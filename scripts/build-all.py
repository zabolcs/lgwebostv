#!/usr/bin/env python3
"""Cross-platform, deterministic IPK builder for the local LG TV applications."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"

LAUNCHER_FILES = (
    "app.js",
    "appinfo.json",
    "index.html",
    "launcher-cache.js",
    "launcher-host.js",
    "launcher.css",
    "launcher-quick-core.js",
    "launcher-ui.js",
    "launcher-runtime.js",
    "launcher-popup-lifecycle.js",
    "icon.svg",
    "icon-large.svg",
    "icon.png",
    "icon-large.png",
    "splash-black.png",
)

APPS = {
    "media-overlay": {
        "id": "hu.szabi.mediaoverlay",
        "files": (
            "app.js",
            "appinfo.json",
            "core.js",
            "index.html",
            "style.css",
            "icon.png",
            "icon-large.png",
        ),
    },
    "camera-viewer": {
        "id": "hu.szabi.cameraviewer",
        "files": (
            "app.js",
            "appinfo.json",
            "index.html",
            "styles.css",
            "icon.png",
            "icon-large.png",
        ),
    },
    "remote-mapper": {
        "id": "hu.szabi.remotemapper",
        "files": (
            "app.js",
            "appinfo.json",
            "index.html",
            "remote-ui.css",
            "remote-ui.js",
            "icon.png",
            "icon-large.png",
        ),
    },
    "launcher": {
        "id": "hu.szabi.launcher",
        "source": "launcher",
        "host": "full",
        "files": LAUNCHER_FILES,
    },
    "launcher-overlay": {
        "id": "hu.szabi.launcher.overlay",
        "source": "launcher",
        "manifest": "launcher-overlay/appinfo.json",
        "host": "full-overlay",
        "files": LAUNCHER_FILES,
    },
    "launcher-quick": {
        "id": "hu.szabi.launcher.quick",
        "source": "launcher",
        "manifest": "launcher-quick/appinfo.json",
        "host": "quick",
        "files": LAUNCHER_FILES,
    },
}

DIAGNOSTIC_APPS = {
    "launcher-startup-probe": {
        "id": "hu.szabi.launcher.startupprobe",
        "source_dir": "tools/launcher-startup-probe",
        "manifest_path": "tools/launcher-startup-probe/appinfo.json",
        "files": (
            "appinfo.json",
            "index.html",
            "icon.png",
            "icon-large.png",
            "splash-black.png",
        ),
        "services": (
            {
                "id": "hu.szabi.launcher.startupprobe.service",
                "source_dir": "tools/launcher-startup-probe/service",
                "files": (
                    "package.json",
                    "services.json",
                    "service-core.js",
                    "service.js",
                ),
            },
        ),
    },
}


def tar_gz(entries: list[tuple[str, bytes | None, int]]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=9, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for name, data, mode in entries:
                info = tarfile.TarInfo(name)
                info.uid = 0
                info.gid = 0
                info.uname = "root"
                info.gname = "root"
                info.mtime = 0
                info.mode = mode
                if data is None:
                    info.type = tarfile.DIRTYPE
                    info.size = 0
                    archive.addfile(info)
                else:
                    info.type = tarfile.REGTYPE
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


def ar_member(name: str, data: bytes) -> bytes:
    encoded_name = (name + "/").encode("ascii")
    if len(encoded_name) > 16:
        raise ValueError(f"ar member name is too long: {name}")
    header = b"".join(
        (
            encoded_name.ljust(16, b" "),
            b"0".ljust(12, b" "),
            b"0".ljust(6, b" "),
            b"0".ljust(6, b" "),
            b"100644".ljust(8, b" "),
            str(len(data)).encode("ascii").ljust(10, b" "),
            b"`\n",
        )
    )
    return header + data + (b"\n" if len(data) % 2 else b"")


def host_config(host: str, app_id: str) -> bytes:
    if host not in {"full", "quick", "full-overlay"}:
        raise ValueError(f"unsupported launcher host: {host}")
    config = json.dumps(
        {"host": host, "appId": app_id},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return f"window.__LAUNCHER_HOST__={config};\n".encode("ascii")


def build(slug: str, config: dict[str, object]) -> tuple[Path, str]:
    source_slug = str(config.get("source", slug))
    source = ROOT / str(config["source_dir"]) if "source_dir" in config else ROOT / "apps" / source_slug
    if "manifest_path" in config:
        appinfo_path = ROOT / str(config["manifest_path"])
    else:
        manifest = str(config.get("manifest", f"{source_slug}/appinfo.json"))
        appinfo_path = ROOT / "apps" / manifest
    appinfo = json.loads(appinfo_path.read_text(encoding="utf-8"))
    expected_id = str(config["id"])
    app_id = str(appinfo.get("id", ""))
    version = str(appinfo.get("version", ""))
    if app_id != expected_id:
        raise ValueError(f"unexpected app id for {slug}: {app_id}")
    version_parts = version.split(".")
    if len(version_parts) != 3 or any(not part.isdigit() for part in version_parts):
        raise ValueError(f"invalid semantic version for {slug}: {version}")

    files: dict[str, bytes] = {}
    for filename in config["files"]:
        filename = str(filename)
        if filename == "launcher-runtime.js":
            # One shared script load avoids four serialized local-file loads on webOS.
            files[filename] = b";\n".join((source / name).read_bytes() for name in
                ("launcher-cache.js", "launcher-quick-core.js", "launcher-popup-lifecycle.js", "launcher-ui.js", "app.js"))
            continue
        path = appinfo_path if filename == "appinfo.json" else source / filename
        if not path.is_file():
            raise FileNotFoundError(f"missing runtime asset: {path}")
        files[filename] = path.read_bytes()
    if "host" in config:
        files["launcher-host.js"] = host_config(str(config["host"]), app_id)
        script_tags = b'<script src="launcher-cache.js"></script><script src="launcher-quick-core.js"></script><script src="launcher-popup-lifecycle.js"></script><script src="launcher-ui.js"></script><script src="app.js"></script>'
        if script_tags not in files["index.html"]:
            raise ValueError("launcher script entry points changed; update the shared bundle")
        files["index.html"] = files["index.html"].replace(script_tags, b'<script src="launcher-runtime.js"></script>')

    service_files: dict[str, dict[str, bytes]] = {}
    for service_config in config.get("services", ()):
        service_id = str(service_config["id"])
        if not service_id.startswith(app_id + "."):
            raise ValueError(f"service id must begin with app id for {slug}: {service_id}")
        service_source = ROOT / str(service_config["source_dir"])
        collected: dict[str, bytes] = {}
        for filename in service_config["files"]:
            filename = str(filename)
            path = service_source / filename
            if not path.is_file():
                raise FileNotFoundError(f"missing service runtime asset: {path}")
            collected[filename] = path.read_bytes()
        service_files[service_id] = collected

    package_metadata = {
        "id": app_id,
        "package_format_version": 2,
        "loc_name": app_id,
        "version": version,
        "vendor": "Szabolcs",
        "app": app_id,
    }
    if service_files:
        package_metadata["services"] = list(service_files)
    packageinfo = (
        json.dumps(
            package_metadata,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    runtime_size = sum(map(len, files.values())) + sum(
        len(data) for service in service_files.values() for data in service.values()
    )
    installed_size = max(1, (runtime_size + len(packageinfo) + 1023) // 1024)
    control = (
        f"Package: {app_id}\n"
        f"Version: {version}\n"
        "Section: misc\n"
        "Priority: optional\n"
        "Architecture: all\n"
        f"Installed-Size: {installed_size}\n"
        "Maintainer: Szabolcs <nobody@example.com>\n"
        "Description: Local webOS picture-in-picture suite application\n"
        "webOS-Package-Format-Version: 2\n"
        "webOS-Packager-Version: 0.3.0\n"
    ).encode("utf-8")

    app_root = f"usr/palm/applications/{app_id}"
    package_root = f"usr/palm/packages/{app_id}"
    directories = [
        "usr",
        "usr/palm",
        "usr/palm/applications",
        app_root,
        "usr/palm/packages",
        package_root,
    ]
    if service_files:
        directories.append("usr/palm/services")
        directories.extend(f"usr/palm/services/{service_id}" for service_id in service_files)
    data_entries: list[tuple[str, bytes | None, int]] = [
        (directory, None, 0o755) for directory in directories
    ]
    data_entries.extend(
        (f"{app_root}/{filename}", data, 0o644)
        for filename, data in files.items()
    )
    for service_id, runtime in service_files.items():
        service_root = f"usr/palm/services/{service_id}"
        data_entries.extend(
            (f"{service_root}/{filename}", data, 0o644)
            for filename, data in runtime.items()
        )
    data_entries.append((f"{package_root}/packageinfo.json", packageinfo, 0o644))

    members = (
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", tar_gz([("control", control, 0o644)])),
        ("data.tar.gz", tar_gz(data_entries)),
    )
    payload = b"!<arch>\n" + b"".join(ar_member(name, data) for name, data in members)
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD / f"{app_id}_{version}_all.ipk"
    temporary = output.with_suffix(output.suffix + ".new")
    temporary.write_bytes(payload)
    os.replace(temporary, output)
    digest = hashlib.sha256(payload).hexdigest()
    return output, digest


def main() -> None:
    for slug, config in APPS.items():
        output, digest = build(slug, config)
        print(f"{digest}  {output}")


if __name__ == "__main__":
    main()
