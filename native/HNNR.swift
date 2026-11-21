// Optional macOS desktop bridge for the official HNNR command. No global input events.
import AppKit
import ApplicationServices
import Foundation

typealias Element = AXUIElement
struct Failure: LocalizedError {
  let message: String
  init(_ text: String) { message = text }
  var errorDescription: String? { message }
}
func value(_ e: Element, _ key: String) -> CFTypeRef? {
  var v: CFTypeRef?
  return AXUIElementCopyAttributeValue(e, key as CFString, &v) == .success ? v : nil
}
func string(_ e: Element, _ key: String) -> String { value(e, key) as? String ?? "" }
func children(_ e: Element) -> [Element] { value(e, "AXChildren") as? [Element] ?? [] }
func first(_ e: Element, _ match: (Element) -> Bool) -> Element? {
  if match(e) { return e }
  for c in children(e) { if let hit = first(c, match) { return hit } }
  return nil
}
func identified(_ e: Element, _ id: String) -> Element? {
  first(e) { string($0, "AXIdentifier") == id }
}
func titles(_ e: Element, _ role: String, _ names: [String]) -> Element? {
  first(e) { string($0, "AXRole") == role && names.contains(string($0, "AXTitle")) }
}
func poll<T>(_ message: String, _ read: () -> T?) throws -> T {
  let end = Date().addingTimeInterval(12)
  repeat {
    if let answer = read() { return answer }
    Thread.sleep(forTimeInterval: 0.12)
  } while Date() < end
  throw Failure(message)
}
func press(_ e: Element) throws {
  guard AXUIElementPerformAction(e, kAXPressAction as CFString) == .success else {
    throw Failure("Phocus 控件没有接受操作")
  }
}
func frame(_ e: Element) throws -> CGRect {
  guard let p = value(e, "AXPosition"), let z = value(e, "AXSize"),
    CFGetTypeID(p) == AXValueGetTypeID(), CFGetTypeID(z) == AXValueGetTypeID()
  else {
    throw Failure("无法读取缩略图或窗口位置")
  }
  var origin = CGPoint.zero
  var size = CGSize.zero
  guard AXValueGetValue(p as! AXValue, .cgPoint, &origin),
    AXValueGetValue(z as! AXValue, .cgSize, &size)
  else {
    throw Failure("窗口几何信息不可用")
  }
  return CGRect(origin: origin, size: size)
}

func contextualClick(pid: pid_t, window: Element, image: Element, scroll: Element) throws {
  let rect = try frame(window)
  let visible = try frame(image).intersection(frame(scroll)).intersection(rect)
  guard visible.width > 2, visible.height > 2 else { throw Failure("请显示缩略图面板和测试副本") }
  let point = CGPoint(x: visible.midX, y: visible.midY)
  let info =
    CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
    as? [[String: Any]] ?? []
  let matches = info.filter { item in
    guard item[kCGWindowOwnerPID as String] as? Int == Int(pid),
      let b = item[kCGWindowBounds as String] as? [String: Double],
      let x = b["X"], let y = b["Y"], let w = b["Width"], let h = b["Height"]
    else { return false }
    return abs(x - rect.minX) < 2 && abs(y - rect.minY) < 2 && abs(w - rect.width) < 2
      && abs(h - rect.height) < 2
  }
  guard matches.count == 1, let number = matches[0][kCGWindowNumber as String] as? Int else {
    throw Failure("无法定位 Phocus 可见主窗口；请保持窗口打开")
  }
  // Window-local coordinates are required for a click delivered to a background window.
  // This macOS symbol is not public API. Fail if unavailable, never click the global screen.
  typealias WindowLocation = @convention(c) (CGEvent, CGPoint) -> Void
  guard let symbol = dlsym(UnsafeMutableRawPointer(bitPattern: -2), "CGEventSetWindowLocation")
  else {
    throw Failure("当前 macOS 缺少窗口定向输入能力")
  }
  let setLocation = unsafeBitCast(symbol, to: WindowLocation.self)
  let local = CGPoint(x: point.x - rect.minX, y: point.y - rect.minY)
  for kind: NSEvent.EventType in [.rightMouseDown, .rightMouseUp] {
    guard
      let event = NSEvent.mouseEvent(
        with: kind, location: CGPoint(x: local.x, y: rect.height - local.y), modifierFlags: [],
        timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: number, context: nil,
        eventNumber: 1, clickCount: 1, pressure: 1)?.cgEvent
    else {
      throw Failure("无法构造 Phocus 窗口事件")
    }
    event.location = point
    setLocation(event, local)
    event.setIntegerValueField(.mouseEventWindowUnderMousePointer, value: Int64(number))
    event.setIntegerValueField(
      .mouseEventWindowUnderMousePointerThatCanHandleThisEvent, value: Int64(number))
    event.postToPid(pid)
    Thread.sleep(forTimeInterval: 0.12)
  }
}

struct Phocus {
  let root: Element
  let pid: pid_t
  init() throws {
    guard AXIsProcessTrusted(), CGPreflightPostEventAccess() else {
      throw Failure("HNNR 桌面桥需要运行客户端具有 macOS 辅助功能权限")
    }
    guard
      let a = NSRunningApplication.runningApplications(withBundleIdentifier: "dk.hasselblad.phocus")
        .first
    else { throw Failure("请先打开 Phocus") }
    pid = a.processIdentifier
    root = AXUIElementCreateApplication(a.processIdentifier)
  }
  var windows: [Element] { value(root, "AXWindows") as? [Element] ?? [] }
  func dialog() -> Element? {
    windows.first { string($0, "AXTitle") == "HNNR" && string($0, "AXSubrole") == "AXDialog" }
  }
  func check(_ folder: String) throws -> Element {
    guard dialog() == nil,
      let w = windows.first(where: {
        string($0, "AXSubrole") == "AXStandardWindow"
          && identified($0, "ThumbnailCollectionView") != nil
      }),
      first(w, { string($0, "AXRole") == "AXSheet" }) == nil
    else { throw Failure("请先完成 Phocus 当前操作或打开主窗口") }
    guard let bar = value(root, "AXMenuBar"), CFGetTypeID(bar) == AXUIElementGetTypeID(),
      let hot = titles(
        bar as! Element, "AXMenuItem", ["自动输出新的图像", "Export New Images Automatically"]),
      string(hot, "AXMenuItemMarkChar").isEmpty
    else { throw Failure("请关闭 Phocus 的「自动输出新的图像」后运行 HNNR") }
    guard
      first(
        w,
        {
          string($0, "AXRole") == "AXPopUpButton" && string($0, "AXIdentifier") == "_NS:148"
            && string($0, "AXValue") == folder
        }) != nil
    else {
      throw Failure("请在 Phocus 中选中 --watch 指定的专用目录")
    }
    return w
  }
  func submit(folder: String, name: String, mode: String) throws {
    let w = try check(folder)
    guard let scroll = identified(w, "ThumbScrollView"),
      let list = identified(scroll, "ThumbnailCollectionView")
    else { throw Failure("缺少缩略图面板") }
    let image: Element = try poll("Phocus 没有显示本次任务的唯一缩略图") {
      let groups = children(list).flatMap(children)
      let thumbnails = groups.filter { identified($0, "ThumbnailTitleView") != nil }
      guard thumbnails.count == 1, let title = identified(thumbnails[0], "ThumbnailTitleView"),
        string(title, "AXValue") == name
      else { return nil }
      return identified(thumbnails[0], "ThumbnailImageView")
    }
    try contextualClick(pid: pid, window: w, image: image, scroll: scroll)
    let item = try poll("后台右键未出现 HNNR 菜单") { identified(list, "runHNNROnSelected:") }
    let menu = value(item, "AXParent")
    var openedDialog = false
    defer {
      if !openedDialog, let menu = menu, CFGetTypeID(menu) == AXUIElementGetTypeID() {
        _ = AXUIElementPerformAction(menu as! Element, "AXCancel" as CFString)
      }
    }
    guard (value(item, "AXEnabled") as? NSNumber)?.boolValue == true else {
      throw Failure("当前照片不支持 HNNR")
    }
    try press(item)
    let panel = try poll("Phocus 没有打开 HNNR 模式窗口") { dialog() }
    openedDialog = true
    var applied = false
    defer {
      if !applied, let close = value(panel, "AXCloseButton"),
        CFGetTypeID(close) == AXUIElementGetTypeID()
      {
        try? press(close as! Element)
      }
    }
    let choices =
      mode == "purity"
      ? ["纯净优先", "Prioritise Purity", "Prioritize Purity"]
      : ["细节优先", "Prioritise Detail", "Prioritize Detail"]
    let labels = children(panel).filter { string($0, "AXRole") == "AXStaticText" }.map {
      string($0, "AXValue")
    }
    guard
      labels.contains(where: {
        $0.range(of: #"(?:：|:)\s*1\s*$"#, options: .regularExpression) != nil
      })
    else { throw Failure("未核实 HNNR 可处理照片数为 1，请检查模式窗口") }
    guard let radio = titles(panel, "AXRadioButton", choices),
      let apply = titles(panel, "AXButton", ["应用", "Apply"])
    else { throw Failure("未识别 HNNR 模式或应用按钮") }
    try press(radio)
    guard (value(radio, "AXValue") as? NSNumber)?.intValue == 1 else {
      throw Failure("HNNR 模式回读失败")
    }
    try press(apply)
    applied = true
  }
}

do {
  let args = Array(CommandLine.arguments.dropFirst())
  let app = try Phocus()
  if args.count == 2 && args[0] == "check" {
    _ = try app.check(args[1])
  } else if args.count == 4 && args[0] == "submit" && ["detail", "purity"].contains(args[3]) {
    try app.submit(folder: args[1], name: args[2], mode: args[3])
  } else {
    throw Failure("invalid helper arguments")
  }
} catch {
  FileHandle.standardError.write(Data((error.localizedDescription + "\n").utf8))
  exit(1)
}
