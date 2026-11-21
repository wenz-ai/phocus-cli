#!/bin/bash
set -euo pipefail
src="$(cd "$(dirname "$0")" && pwd)"
root="$HOME/.local/share/phocus-cli"
mkdir -p "$root/installs" "$HOME/.local/bin"
dest="$(mktemp -d "$root/installs/1.0.0.XXXXXX")"
ready=false
trap 'if [ "$ready" = false ]; then rm -rf "$dest"; fi' EXIT
echo '正在安装 Phocus CLI 和 Codex Skill…'
cp "$src"/{phocus,watermark.py,workspace_paths.py,mcp_server.py} "$dest/"
cp -R "$src/native" "$src/skills" "$dest/"
py=''
for candidate in "$(command -v python3 || true)" /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -x "$candidate" ] && [ "$candidate" != /usr/bin/python3 ] || continue
  if "$candidate" -c 'import sys,venv; sys.exit(not ((3,10)<=sys.version_info[:2]<(3,15)))'; then py="$candidate"; break; fi
done
if [ -n "$py" ]; then
  "$py" -m venv "$dest/.venv"
else
  echo '正在下载独立运行环境…'
  uv="$(command -v uv || true)"
  if [ -z "$uv" ]; then
    uv="$root/tools/uv"
    if [ ! -x "$uv" ]; then
      /usr/bin/curl -fsSL --retry 3 https://astral.sh/uv/install.sh -o "$dest/uv-install.sh"
      UV_UNMANAGED_INSTALL="$root/tools" /bin/sh "$dest/uv-install.sh"
    fi
  fi
  UV_PYTHON_INSTALL_DIR="$root/python" "$uv" venv --seed --python 3.12 "$dest/.venv"
fi
python="$dest/.venv/bin/python"
"$python" -m pip --disable-pip-version-check -q install 'Pillow>=11,<14' 'mcp==1.30.0'
"$python" "$dest/phocus" capabilities >/dev/null
"$python" -c 'from mcp.server.fastmcp import FastMCP; from PIL import ImageCms'
"$python" - "$root" "$dest" <<'PY'
from pathlib import Path
from shlex import quote
import os,sys,tempfile
root,dest=map(Path,sys.argv[1:])
current=root/'current'
bin_file=Path.home()/'.local/bin/phocus'
skill=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex')/'skills/phocus-photo'
skill_target=current/'skills/phocus-photo'
if skill.exists() or skill.is_symlink():
    if not skill.is_symlink() or os.readlink(skill)!=str(skill_target):
        sys.exit(f'同名 Skill 已存在，请先为已有版本改名：{skill}')
if bin_file.exists() and (not bin_file.is_file() or str(root) not in bin_file.read_text(errors="replace")):
    sys.exit(f'发现其他程序使用了 {bin_file}，请先改名。')
if current.exists() and not current.is_symlink():sys.exit(f'{current} 已被其他目录占用')
sys.path.insert(0,str(dest))
from workspace_paths import read_paths,save_paths
paths=read_paths()
save_paths(paths)
skill.parent.mkdir(parents=True,exist_ok=True)
# Prepare entry points before switching a previous installation to the new environment.
with tempfile.TemporaryDirectory(dir=bin_file.parent) as tmp:
    wrapper=Path(tmp)/'phocus'
    wrapper.write_text('#!/bin/sh\nexec '+quote(str(current/'.venv/bin/python'))+' '+quote(str(current/'phocus'))+' "$@"\n')
    wrapper.chmod(0o755)
    if not skill.is_symlink():skill.symlink_to(skill_target,target_is_directory=True)
    os.replace(wrapper,bin_file)
with tempfile.TemporaryDirectory(dir=root) as tmp:
    link=Path(tmp)/'current';link.symlink_to(dest,target_is_directory=True);os.replace(link,current)
PY
ready=true
case ":${PATH:-}:" in
  *":$HOME/.local/bin:"*) ;;
  *) case "${SHELL:-/bin/zsh}" in
       */zsh) profile="$HOME/.zprofile";;
       */bash) profile="$HOME/.bash_profile";;
       *) profile='';;
     esac
     if [ -n "$profile" ] && ! grep -Fqs 'export PATH="$HOME/.local/bin:$PATH"' "$profile"; then
       printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$profile"
     fi ;;
esac
"$HOME/.local/bin/phocus" --version
echo '安装完成。新开一个 Codex 对话，即可用 $phocus-photo 处理照片。'
echo '工作目录如下：'
"$HOME/.local/bin/phocus" paths
