#!/usr/bin/env python3
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

CHECKPOINT = Path(os.environ.get("CHECKPOINT_DIR", "checkpoint")).resolve()
AMNEZIA_SOURCE = Path(os.environ.get("AMNEZIA_SOURCE_DIR", "amnezia-source")).resolve()
EVIDENCE = Path(os.environ.get("EVIDENCE_DIR", "evidence")).resolve()
EVIDENCE.mkdir(parents=True, exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="six-package-provenance-"))

EXPECTED = {
    "amnezia-vpn-offline": "4.8.21.0",
    "windscribe-cli": "2.23.12",
    "sing-box": "1.13.18",
    "xray-offline": "26.3.27",
    "visual-studio-code-offline": "1.133.0",
    "tor-browser-offline": "15.0.19",
}

report: dict[str, Any] = {
    "schema": 1,
    "checkpoint": str(CHECKPOINT),
    "amnezia_source": str(AMNEZIA_SOURCE),
    "packages": {},
    "checkpoint_manifest": {},
}


def run(args: list[str], *, cwd: Path | None = None, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=check,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cp = run(["curl", "-fL", "--retry", "5", "--retry-all-errors", "--connect-timeout", "30", url, "-o", str(dest)], check=False)
    if cp.returncode != 0:
        raise RuntimeError(f"download failed: {url}\n{cp.stdout}")


def fetch_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "cachy-provenance-verifier/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def github_asset(repo: str, tag: str, name: str, dest: Path) -> dict[str, Any]:
    rel = fetch_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    if not rel.get("immutable", False):
        raise RuntimeError(f"GitHub release {repo}@{tag} is not immutable")
    matches = [a for a in rel.get("assets", []) if a.get("name") == name]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one asset {name!r} in {repo}@{tag}, found {len(matches)}")
    a = matches[0]
    digest = a.get("digest")
    if not isinstance(digest, str) or not digest.startswith("sha256:"):
        raise RuntimeError(f"asset {name} has no GitHub-published SHA-256 digest")
    download(a["browser_download_url"], dest)
    actual = sha256(dest)
    expected = digest.split(":", 1)[1]
    if actual != expected:
        raise RuntimeError(f"vendor digest mismatch for {name}: {actual} != {expected}")
    if dest.stat().st_size != int(a["size"]):
        raise RuntimeError(f"vendor size mismatch for {name}: {dest.stat().st_size} != {a['size']}")
    return {
        "repository": repo,
        "tag": tag,
        "release_id": rel.get("id"),
        "release_immutable": True,
        "asset_id": a.get("id"),
        "asset_name": name,
        "asset_size": a.get("size"),
        "published_sha256": expected,
        "downloaded_sha256": actual,
        "downloaded_size": dest.stat().st_size,
    }


def pkginfo(path: Path) -> dict[str, str]:
    cp = run(["bsdtar", "-xOf", str(path), ".PKGINFO"])
    out: dict[str, str] = {}
    for line in cp.stdout.splitlines():
        if " = " in line:
            k, v = line.split(" = ", 1)
            if k in {"pkgname", "pkgver", "arch"}:
                out[k] = v
    return out


def discover_packages() -> dict[str, Path]:
    found: dict[str, Path] = {}
    all_pkgs = sorted(CHECKPOINT.rglob("*.pkg.tar.zst"))
    for p in all_pkgs:
        info = pkginfo(p)
        name = info.get("pkgname")
        if name in EXPECTED:
            if name in found:
                raise RuntimeError(f"duplicate expected package {name}: {found[name]} and {p}")
            found[name] = p
    missing = sorted(set(EXPECTED) - set(found))
    if missing:
        raise RuntimeError(f"checkpoint missing packages: {missing}; all package files={len(all_pkgs)}")
    return found


def extract_pkg(path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    run(["bsdtar", "-xf", str(path), "-C", str(dest)])


def tree_manifest(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise RuntimeError(f"tree root missing: {root}")
    m: dict[str, dict[str, Any]] = {}
    for p in sorted(root.rglob("*"), key=lambda x: x.as_posix()):
        rel = p.relative_to(root).as_posix()
        st = p.lstat()
        mode = stat.S_IMODE(st.st_mode)
        if p.is_symlink():
            m[rel] = {"type": "symlink", "target": os.readlink(p), "mode": mode}
        elif p.is_file():
            m[rel] = {"type": "file", "sha256": sha256(p), "size": st.st_size, "mode": mode}
        elif p.is_dir():
            m[rel] = {"type": "dir", "mode": mode}
        else:
            m[rel] = {"type": "other", "mode": mode}
    return m


def compare_trees(source: Path, packaged: Path, label: str) -> dict[str, Any]:
    a = tree_manifest(source)
    b = tree_manifest(packaged)
    differences: list[dict[str, Any]] = []
    for rel in sorted(set(a) | set(b)):
        av = a.get(rel)
        bv = b.get(rel)
        if av != bv:
            differences.append({"path": rel, "source": av, "packaged": bv})
    (EVIDENCE / f"{label}-source-manifest.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n")
    (EVIDENCE / f"{label}-packaged-manifest.json").write_text(json.dumps(b, indent=2, sort_keys=True) + "\n")
    return {
        "identical": not differences,
        "source_entries": len(a),
        "packaged_entries": len(b),
        "difference_count": len(differences),
        "differences": differences[:100],
        "differences_truncated": len(differences) > 100,
    }


def compare_file(source: Path, packaged: Path) -> dict[str, Any]:
    if not source.is_file() or not packaged.is_file():
        return {
            "identical": False,
            "source_exists": source.is_file(),
            "packaged_exists": packaged.is_file(),
        }
    a = sha256(source)
    b = sha256(packaged)
    cmp_rc = subprocess.run(["cmp", "-s", str(source), str(packaged)]).returncode
    return {
        "identical": cmp_rc == 0,
        "source_sha256": a,
        "packaged_sha256": b,
        "source_size": source.stat().st_size,
        "packaged_size": packaged.stat().st_size,
        "cmp_exit_code": cmp_rc,
    }


def package_base(name: str, path: Path) -> dict[str, Any]:
    info = pkginfo(path)
    version = info.get("pkgver", "").split("-", 1)[0]
    if version != EXPECTED[name]:
        raise RuntimeError(f"{name} version {version!r} != expected {EXPECTED[name]!r}")
    return {
        "package_path": str(path.relative_to(CHECKPOINT)),
        "package_sha256": sha256(path),
        "package_size": path.stat().st_size,
        "pkginfo": info,
    }


def verify_checkpoint_manifest(packages: dict[str, Path]) -> None:
    manifests = list(CHECKPOINT.rglob("EXTERNAL-SHA256SUMS"))
    if len(manifests) != 1:
        report["checkpoint_manifest"] = {"status": "FAIL", "reason": f"expected one EXTERNAL-SHA256SUMS, found {len(manifests)}"}
        return
    mf = manifests[0]
    entries: dict[str, str] = {}
    for line in mf.read_text().splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            entries[Path(parts[1].lstrip("* ")).name] = parts[0]
    mismatches = []
    for p in packages.values():
        expected = entries.get(p.name)
        actual = sha256(p)
        if expected != actual:
            mismatches.append({"file": p.name, "manifest": expected, "actual": actual})
    report["checkpoint_manifest"] = {
        "status": "PASS" if not mismatches else "FAIL",
        "path": str(mf.relative_to(CHECKPOINT)),
        "entries": len(entries),
        "mismatches": mismatches,
    }


def verify_windscribe(pkg: Path) -> dict[str, Any]:
    r = package_base("windscribe-cli", pkg)
    vendor = WORK / "windscribe.pkg.tar.zst"
    v = github_asset("Windscribe/Desktop-App", "v2.23.12", "windscribe-cli_2.23.12_amd64.pkg.tar.zst", vendor)
    identity = compare_file(vendor, pkg)
    r.update({"upstream": v, "whole_package_identity": identity})
    r["status"] = "STRICT_PASS" if identity["identical"] else "FAIL"
    return r


def verify_singbox(pkg: Path) -> dict[str, Any]:
    r = package_base("sing-box", pkg)
    vendor = WORK / "sing-box.pkg.tar.zst"
    v = github_asset("SagerNet/sing-box", "v1.13.18", "sing-box_1.13.18_linux_x86_64.pkg.tar.zst", vendor)
    identity = compare_file(vendor, pkg)
    r.update({"upstream": v, "whole_package_identity": identity})
    r["status"] = "STRICT_PASS" if identity["identical"] else "FAIL"
    return r


def verify_xray(pkg: Path) -> dict[str, Any]:
    r = package_base("xray-offline", pkg)
    vendor_zip = WORK / "Xray-linux-64.zip"
    v = github_asset("XTLS/Xray-core", "v26.3.27", "Xray-linux-64.zip", vendor_zip)
    src = WORK / "xray-src"
    src.mkdir()
    with zipfile.ZipFile(vendor_zip) as z:
        z.extractall(src)
    dst = WORK / "xray-pkg"
    extract_pkg(pkg, dst)
    payload = {
        "xray": compare_file(src / "xray", dst / "usr/bin/xray"),
        "geoip.dat": compare_file(src / "geoip.dat", dst / "usr/share/xray/geoip.dat"),
        "geosite.dat": compare_file(src / "geosite.dat", dst / "usr/share/xray/geosite.dat"),
    }
    r.update({"upstream": v, "payload_identity": payload})
    r["status"] = "STRICT_PASS" if all(x.get("identical") for x in payload.values()) else "FAIL"
    return r


def find_amnezia_run() -> Path:
    candidates = [p for p in AMNEZIA_SOURCE.rglob("*") if p.is_file() and (p.name == "AmneziaVPN.run" or p.suffix == ".run")]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one Amnezia .run in source artifact, found {len(candidates)}: {[str(x) for x in candidates[:20]]}")
    return candidates[0]


def verify_amnezia(pkg: Path) -> dict[str, Any]:
    r = package_base("amnezia-vpn-offline", pkg)
    dst = WORK / "amnezia-pkg"
    extract_pkg(pkg, dst)
    built = find_amnezia_run()
    embedded = dst / "usr/lib/amnezia-offline/AmneziaVPN.run"
    preservation = compare_file(built, embedded)

    vendor = WORK / "AmneziaVPN_Linux_Installer.bin"
    v = github_asset("amnezia-vpn/amnezia-client", "4.8.21.0", "AmneziaVPN_Linux_Installer.bin", vendor)
    vendor_vs_built = compare_file(vendor, built)
    vendor_vs_embedded = compare_file(vendor, embedded)
    r.update({
        "upstream": v,
        "source_build_to_packaged_identity": preservation,
        "vendor_release_to_source_build_identity": vendor_vs_built,
        "vendor_release_to_packaged_identity": vendor_vs_embedded,
    })
    if preservation["identical"] and vendor_vs_embedded["identical"]:
        r["status"] = "STRICT_PASS"
    elif preservation["identical"]:
        r["status"] = "PRESERVATION_PASS_STRICT_FAIL"
    else:
        r["status"] = "FAIL"
    return r


def verify_tor(pkg: Path) -> dict[str, Any]:
    r = package_base("tor-browser-offline", pkg)
    base = "https://dist.torproject.org/torbrowser/15.0.19"
    archive = WORK / "tor-browser-linux-x86_64-15.0.19.tar.xz"
    signature = WORK / (archive.name + ".asc")
    download(f"{base}/{archive.name}", archive)
    download(f"{base}/{signature.name}", signature)

    gnupg = WORK / "tor-gnupg"
    gnupg.mkdir(mode=0o700)
    env = os.environ.copy()
    env["GNUPGHOME"] = str(gnupg)
    locate = subprocess.run(
        ["gpg", "--batch", "--auto-key-locate", "nodefault,wkd", "--locate-keys", "torbrowser@torproject.org"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if locate.returncode != 0:
        raise RuntimeError(f"Tor WKD key lookup failed: {locate.stdout}")
    fpr_cp = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--fingerprint", "torbrowser@torproject.org"],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True,
    )
    fingerprints = [line.split(":")[9] for line in fpr_cp.stdout.splitlines() if line.startswith("fpr:")]
    expected_fpr = "EF6E286DDA85EA2A4BA7DE684E2C6E8793298290"
    if expected_fpr not in fingerprints:
        raise RuntimeError(f"Tor signing key fingerprint mismatch: {fingerprints}")
    verify = subprocess.run(
        ["gpg", "--batch", "--verify", str(signature), str(archive)],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    if verify.returncode != 0:
        raise RuntimeError(f"Tor detached signature verification failed: {verify.stdout}")

    src_parent = WORK / "tor-src"
    src_parent.mkdir()
    run(["tar", "-xJf", str(archive), "-C", str(src_parent)])
    src = src_parent / "tor-browser"
    dst_parent = WORK / "tor-pkg"
    extract_pkg(pkg, dst_parent)
    dst = dst_parent / "opt/tor-browser"
    identity = compare_trees(src, dst, "tor-browser")
    r.update({
        "upstream": {
            "archive": archive.name,
            "downloaded_sha256": sha256(archive),
            "downloaded_size": archive.stat().st_size,
            "signature": signature.name,
            "signature_verified": True,
            "signing_fingerprint": expected_fpr,
            "wkd_fingerprints": fingerprints,
        },
        "payload_tree_identity": identity,
    })
    r["status"] = "STRICT_PASS" if identity["identical"] else "FAIL"
    return r


def fetch_vscode_rpm(version: str, dest: Path) -> dict[str, Any]:
    base = "https://packages.microsoft.com/yumrepos/vscode/"
    repomd = WORK / "vscode-repomd.xml"
    download(base + "repodata/repomd.xml", repomd)
    root = ET.parse(repomd).getroot()
    primary_href = None
    for data in root.findall("{http://linux.duke.edu/metadata/repo}data"):
        if data.attrib.get("type") == "primary":
            loc = data.find("{http://linux.duke.edu/metadata/repo}location")
            if loc is not None:
                primary_href = loc.attrib.get("href")
                break
    if not primary_href:
        raise RuntimeError("VS Code yum repo has no primary metadata")
    primary = WORK / Path(primary_href).name
    download(base + primary_href, primary)
    raw = primary.read_bytes()
    if primary.name.endswith(".gz"):
        xml_bytes = gzip.decompress(raw)
    elif primary.name.endswith(".zst"):
        out = WORK / "primary.xml"
        run(["zstd", "-d", "-f", str(primary), "-o", str(out)])
        xml_bytes = out.read_bytes()
    else:
        xml_bytes = raw
    proot = ET.fromstring(xml_bytes)
    common = "http://linux.duke.edu/metadata/common"
    candidates = []
    for p in proot.findall(f"{{{common}}}package"):
        name = p.findtext(f"{{{common}}}name")
        arch = p.findtext(f"{{{common}}}arch")
        ver = p.find(f"{{{common}}}version")
        loc = p.find(f"{{{common}}}location")
        if name == "code" and arch == "x86_64" and ver is not None and ver.attrib.get("ver") == version and loc is not None:
            candidates.append((ver.attrib, loc.attrib.get("href")))
    if len(candidates) != 1:
        raise RuntimeError(f"expected one signed VS Code RPM for {version}, found {candidates}")
    verattrs, href = candidates[0]
    assert href
    download(base + href, dest)

    key = WORK / "microsoft.asc"
    download("https://packages.microsoft.com/keys/microsoft.asc", key)
    show = run(["gpg", "--batch", "--with-colons", "--show-keys", "--fingerprint", str(key)])
    fps = [line.split(":")[9] for line in show.stdout.splitlines() if line.startswith("fpr:")]
    expected_fp = "BC528686B50D79E339D3721CEB3E94ADBE1229CF"
    if expected_fp not in fps:
        raise RuntimeError(f"Microsoft signing-key fingerprint mismatch: {fps}")
    run(["sudo", "rpm", "--import", str(key)])
    sig = run(["rpmkeys", "--checksig", "--verbose", str(dest)], check=False)
    if sig.returncode != 0 or "Signature" not in sig.stdout or "OK" not in sig.stdout:
        raise RuntimeError(f"Microsoft RPM signature verification failed: {sig.stdout}")
    return {
        "repository": base,
        "rpm_location": href,
        "rpm_sha256": sha256(dest),
        "rpm_size": dest.stat().st_size,
        "rpm_version_metadata": verattrs,
        "signing_key_fingerprint": expected_fp,
        "signature_check": sig.stdout.strip(),
    }


def verify_vscode(pkg: Path) -> dict[str, Any]:
    r = package_base("visual-studio-code-offline", pkg)
    tarball = WORK / "vscode-1.133.0-linux-x64.tar.gz"
    download("https://update.code.visualstudio.com/1.133.0/linux-x64/stable", tarball)
    src_parent = WORK / "vscode-src"
    src_parent.mkdir()
    run(["tar", "-xzf", str(tarball), "-C", str(src_parent)])
    src = src_parent / "VSCode-linux-x64"
    dst_parent = WORK / "vscode-pkg"
    extract_pkg(pkg, dst_parent)
    dst = dst_parent / "opt/visual-studio-code"
    tar_identity = compare_trees(src, dst, "vscode-tar-to-package")

    rpm_path = WORK / "code-1.133.0.x86_64.rpm"
    rpm_evidence = fetch_vscode_rpm("1.133.0", rpm_path)
    rpm_root = WORK / "vscode-rpm"
    rpm_root.mkdir()
    cmd = f"cd {shlex_quote(str(rpm_root))} && rpm2cpio {shlex_quote(str(rpm_path))} | cpio -idm --quiet"
    cp = subprocess.run(["bash", "-lc", cmd], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if cp.returncode != 0:
        raise RuntimeError(f"RPM extraction failed: {cp.stdout}")
    rpm_tree = rpm_root / "usr/share/code"
    rpm_vs_tar = compare_trees(rpm_tree, src, "vscode-signed-rpm-to-tar")

    r.update({
        "upstream_tarball": {
            "url": "https://update.code.visualstudio.com/1.133.0/linux-x64/stable",
            "downloaded_sha256": sha256(tarball),
            "downloaded_size": tarball.stat().st_size,
        },
        "tarball_to_packaged_tree_identity": tar_identity,
        "signed_rpm": rpm_evidence,
        "signed_rpm_to_tarball_tree_identity": rpm_vs_tar,
    })
    r["status"] = "STRICT_PASS" if tar_identity["identical"] and rpm_vs_tar["identical"] else ("PARTIAL" if tar_identity["identical"] else "FAIL")
    return r


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def safe_verify(name: str, fn, pkg: Path) -> None:
    try:
        report["packages"][name] = fn(pkg)
    except Exception as e:
        report["packages"][name] = {
            "status": "FAIL",
            "error": f"{type(e).__name__}: {e}",
        }


def main() -> int:
    try:
        packages = discover_packages()
    except Exception as e:
        report["fatal"] = f"{type(e).__name__}: {e}"
        (EVIDENCE / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        return 2

    verify_checkpoint_manifest(packages)
    safe_verify("windscribe-cli", verify_windscribe, packages["windscribe-cli"])
    safe_verify("sing-box", verify_singbox, packages["sing-box"])
    safe_verify("xray-offline", verify_xray, packages["xray-offline"])
    safe_verify("visual-studio-code-offline", verify_vscode, packages["visual-studio-code-offline"])
    safe_verify("tor-browser-offline", verify_tor, packages["tor-browser-offline"])
    safe_verify("amnezia-vpn-offline", verify_amnezia, packages["amnezia-vpn-offline"])

    strict_ok = report["checkpoint_manifest"].get("status") == "PASS" and all(
        report["packages"].get(name, {}).get("status") == "STRICT_PASS" for name in EXPECTED
    )
    report["strict_all_six"] = strict_ok
    report["status_counts"] = {}
    for item in report["packages"].values():
        s = item.get("status", "UNKNOWN")
        report["status_counts"][s] = report["status_counts"].get(s, 0) + 1

    (EVIDENCE / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    lines = [
        "Six-package provenance verification",
        f"checkpoint manifest: {report['checkpoint_manifest'].get('status')}",
    ]
    for name in EXPECTED:
        item = report["packages"].get(name, {})
        lines.append(f"{name}: {item.get('status')}" + (f" -- {item.get('error')}" if item.get("error") else ""))
    lines.append(f"strict_all_six: {strict_ok}")
    (EVIDENCE / "report.txt").write_text("\n".join(lines) + "\n")
    if strict_ok:
        (EVIDENCE / "STRICT_SUCCESS").write_text("all six packages passed strict provenance verification\n")
    print("\n".join(lines))
    return 0 if strict_ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        shutil.rmtree(WORK, ignore_errors=True)
