"""Resumable batches publish one photo and its receipt in the same rename."""
import json
import os
import re
import tempfile
from pathlib import Path


def _save(path, obj):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        json.dump(obj, stream, ensure_ascii=False)
        name = stream.name
    os.replace(name, path)


def _relocate_result(row, old, new):
    for key in ("output", "sidecar"):
        if key in row:
            row[key] = str(new / Path(row[key]).relative_to(old))
    if "delivery" in row:
        _relocate_result(row["delivery"], old, new)


def run_batch(sources, output, batch_id, recipe, process, lock):
    if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", batch_id) is None:
        raise ValueError("批次名称请用 1–64 个英文字母、数字、下划线或短横线")
    directory = output / ("batch-" + batch_id)
    if directory.is_symlink():
        raise ValueError("批次目录不能是符号链接")
    signature = json.loads(
        json.dumps({"sources": list(map(str, sources)), "recipe": recipe}, default=str)
    )
    rows = []
    with lock("batch-" + batch_id + ".lock"):
        directory.mkdir(parents=True, exist_ok=True)
        manifest = directory / "recipe.json"
        if manifest.is_file():
            if json.loads(manifest.read_text()) != signature:
                raise ValueError("同一批次须使用相同的文件顺序及配方；新任务请换一个批次名称")
        elif any(directory.iterdir()):
            raise ValueError("同名目录已有其他文件，请更换批次名称")
        else:
            _save(manifest, signature)
        for index, source in enumerate(sources):
            dest = directory / f"{index+1:05d}"
            receipt = dest / "result.json"
            if dest.is_symlink():
                raise ValueError("批次结果目录不能是符号链接")
            if dest.exists():
                row = json.loads(receipt.read_text())
                outputs = [row["output"]]
                if "sidecar" in row:
                    outputs.append(row["sidecar"])
                if "delivery" in row:
                    outputs.append(row["delivery"]["output"])
                if not all(
                    Path(path).resolve().is_relative_to(dest) and Path(path).is_file()
                    for path in outputs
                ):
                    raise ValueError("已有批次的交付文件已移动或删除，请恢复文件或使用新的批次名称")
                rows.append(dict(row, status="completed"))
                continue
            try:
                with tempfile.TemporaryDirectory(
                    prefix=".stage-", dir=directory
                ) as tmp:
                    stage = Path(tmp) / "item"
                    stage.mkdir()
                    row = process(source, stage)
                    _relocate_result(row, stage, dest)
                    _save(stage / "result.json", row)
                    stage.rename(dest)
            except (ValueError, OSError) as exc:
                rows.append(dict(source=str(source), status="failed", error=str(exc)))
                rows.extend(
                    dict(source=str(p), status="pending") for p in sources[index + 1 :]
                )
                break
            rows.append(dict(row, status="completed"))
    return rows
