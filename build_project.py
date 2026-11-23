#!/usr/bin/env python3
"""ClipPulse Android project orchestrator for GitHub Actions."""

from __future__ import annotations

import glob
import os
import shutil
import sys
from typing import Dict, List, Tuple

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from parts import (  # noqa: E402
    part_ai,
    part_core,
    part_export,
    part_gradle,
    part_scan,
    part_storage,
    part_ui_1,
    part_ui_2,
)

ABI_TO_TRIPLE: Dict[str, str] = {
    "arm64-v8a": "aarch64-linux-android",
    "armeabi-v7a": "arm-linux-androideabi",
    "x86_64": "x86_64-linux-android",
    "x86": "i686-linux-android",
}


def write_text_file(rel_path: str, content: str) -> None:
    full_path = os.path.join(ROOT_DIR, rel_path)
    parent = os.path.dirname(full_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(full_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def resolve_android_sdk() -> str:
    for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        val = os.environ.get(env_key, "").strip()
        if val and os.path.isdir(val):
            return val
    default_sdk = "/usr/local/lib/android/sdk"
    if os.path.isdir(default_sdk):
        return default_sdk
    raise RuntimeError("ANDROID_HOME / ANDROID_SDK_ROOT is not set or directory does not exist.")


def write_local_properties(sdk_dir: str) -> None:
    escaped = sdk_dir.replace("\\", "\\\\").replace(":", "\\:")
    write_text_file("local.properties", f"sdk.dir={escaped}\n")
    print(f"[build_project] Wrote local.properties -> {sdk_dir}")


def _version_sort_key(path: str) -> Tuple[int, ...]:
    base = os.path.basename(path)
    parts: List[int] = []
    for token in base.replace("-", ".").split("."):
        if token.isdigit():
            parts.append(int(token))
    return tuple(parts)


def resolve_ndk_dir(sdk_dir: str) -> str:
    for env_key in ("ANDROID_NDK_HOME", "ANDROID_NDK_ROOT", "ANDROID_NDK_LATEST_HOME"):
        val = os.environ.get(env_key, "").strip()
        if val and os.path.isdir(val):
            return val
    ndk_root = os.path.join(sdk_dir, "ndk")
    if os.path.isdir(ndk_root):
        candidates = [
            os.path.join(ndk_root, entry)
            for entry in os.listdir(ndk_root)
            if os.path.isdir(os.path.join(ndk_root, entry))
        ]
        if candidates:
            candidates.sort(key=_version_sort_key, reverse=True)
            return candidates[0]
    ndk_bundle = os.path.join(sdk_dir, "ndk-bundle")
    if os.path.isdir(ndk_bundle):
        return ndk_bundle
    raise RuntimeError(f"Could not locate Android NDK inside {sdk_dir} or environment variables.")


def copy_ndk_libcpp(sdk_dir: str) -> None:
    ndk_dir = resolve_ndk_dir(sdk_dir)
    print(f"[build_project] Using NDK: {ndk_dir}")
    for abi, triple in ABI_TO_TRIPLE.items():
        pattern = os.path.join(
            ndk_dir,
            "toolchains",
            "llvm",
            "prebuilt",
            "*",
            "sysroot",
            "usr",
            "lib",
            triple,
            "libc++_shared.so",
        )
        matches = glob.glob(pattern)
        if not matches:
            fallback_pattern = os.path.join(
                ndk_dir,
                "sources",
                "cxx-stl",
                "llvm-libc++",
                "libs",
                abi,
                "libc++_shared.so",
            )
            matches = glob.glob(fallback_pattern)
        if not matches:
            raise RuntimeError(f"libc++_shared.so not found for ABI {abi} ({triple}) in {ndk_dir}")

        src_so = matches[0]
        dst_so = os.path.join(ROOT_DIR, "app", "src", "main", "jniLibs", abi, "libc++_shared.so")
        parent = os.path.dirname(dst_so)
        if parent:
            os.makedirs(parent, exist_ok=True)
        shutil.copy2(src_so, dst_so)
        print(f"[build_project] Copied libc++_shared.so for {abi} -> {dst_so}")


def write_all_parts() -> None:
    part_modules = [
        ("part_gradle", part_gradle),
        ("part_core", part_core),
        ("part_ai", part_ai),
        ("part_scan", part_scan),
        ("part_export", part_export),
        ("part_storage", part_storage),
        ("part_ui_1", part_ui_1),
        ("part_ui_2", part_ui_2),
    ]
    seen_paths: Dict[str, str] = {}
    total = 0
    for name, mod in part_modules:
        files_dict = getattr(mod, "FILES", None)
        if not isinstance(files_dict, dict) or not files_dict:
            raise RuntimeError(f"Module {name} does not expose a non-empty FILES dict.")
        for rel_path, content in files_dict.items():
            if rel_path in seen_paths:
                raise RuntimeError(
                    f"Duplicate file path '{rel_path}' in {name} and {seen_paths[rel_path]}"
                )
            seen_paths[rel_path] = name
            write_text_file(rel_path, content.lstrip("\n"))
            total += 1
    print(f"[build_project] Wrote {total} project files across {len(part_modules)} parts.")


def main() -> None:
    sdk_dir = resolve_android_sdk()
    write_local_properties(sdk_dir)
    copy_ndk_libcpp(sdk_dir)
    write_all_parts()
    print("[build_project] Project generation completed successfully.")


if __name__ == "__main__":
    main()
