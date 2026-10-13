#!/usr/bin/env python3
"""Create independently installable Android APK clones with apktool.

The tool changes the application package, relocates matching smali classes,
updates package-dependent XML/smali strings, changes the launcher label and
version, rebuilds, zipaligns, signs, and verifies each clone.

It is intended for APKs you are authorized to modify. Some APKs cannot be
cloned safely because of native JNI package bindings, signature checks,
Play Integrity, encrypted code, or server-side package allowlists.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

TEXT_SUFFIXES = {
    ".xml", ".smali", ".yml", ".yaml", ".txt", ".json", ".properties",
    ".html", ".htm", ".js", ".css", ".java", ".kt", ".cfg", ".conf",
    ".ini", ".pro", ".gradle", ".kts", ".md", ".csv",
}

PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


class CloneError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloneSpec:
    number: int
    app_name: str
    package_name: str
    version_code: int
    version_name: str
    output_apk: str


@dataclass
class CloneReport:
    spec: dict
    base_package: str
    base_version_code: int
    base_version_name: str
    replacements: dict[str, str]
    package_refs_replaced: int
    slash_refs_replaced: int
    app_name_files_updated: int
    relocated_smali_roots: list[str]
    apk_sha256: str
    apk_size: int
    aapt2_badging: str
    signature_summary: str
    warnings: list[str]


def run(cmd: Sequence[str | os.PathLike[str]], *, cwd: Path | None = None,
        capture: bool = True, check: bool = True) -> subprocess.CompletedProcess[str]:
    printable = " ".join(str(x) for x in cmd)
    print(f"+ {printable}", flush=True)
    result = subprocess.run(
        [str(x) for x in cmd], cwd=str(cwd) if cwd else None,
        text=True, stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and result.returncode != 0:
        output = result.stdout or ""
        raise CloneError(f"Command failed ({result.returncode}): {printable}\n{output[-8000:]}")
    return result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_executable(explicit: str | None, name: str) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise CloneError(f"{name} not found: {p}")
        return p
    found = shutil.which(name)
    if not found:
        raise CloneError(f"Required executable not found: {name}")
    return Path(found).resolve()


def find_build_tool(explicit: str | None, sdk_root: Path | None, name: str) -> Path:
    if explicit:
        return find_executable(explicit, name)
    if sdk_root:
        bt = sdk_root / "build-tools"
        if bt.is_dir():
            candidates: list[tuple[tuple[int, ...], Path]] = []
            for version_dir in bt.iterdir():
                tool = version_dir / name
                if tool.exists():
                    nums = tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[._-]", version_dir.name))
                    candidates.append((nums, tool))
            if candidates:
                return sorted(candidates, reverse=True)[0][1].resolve()
    return find_executable(None, name)


def apktool_command(apktool: Path, java: Path) -> list[str]:
    if apktool.suffix.lower() == ".jar":
        return [str(java), "-jar", str(apktool)]
    return [str(apktool)]


def decode_apk(apk: Path, project: Path, apktool: Path, java: Path) -> None:
    cmd = apktool_command(apktool, java) + ["d", "-f", str(apk), "-o", str(project)]
    run(cmd)


def build_apk(project: Path, unsigned_apk: Path, apktool: Path, java: Path) -> None:
    cmd = apktool_command(apktool, java) + ["b", str(project), "-o", str(unsigned_apk)]
    run(cmd)


def parse_manifest_package(manifest: Path) -> str:
    text = manifest.read_text(encoding="utf-8")
    m = re.search(r"\bpackage=\"([^\"]+)\"", text)
    if not m:
        raise CloneError("Cannot find manifest package in decoded AndroidManifest.xml")
    return m.group(1)


def parse_apktool_version(apktool_yml: Path) -> tuple[int, str]:
    text = apktool_yml.read_text(encoding="utf-8")
    code_m = re.search(r"(?m)^\s*versionCode:\s*['\"]?([^'\"\s]+)", text)
    name_m = re.search(r"(?m)^\s*versionName:\s*(.+?)\s*$", text)
    if not code_m or not name_m:
        raise CloneError("Cannot parse versionInfo from apktool.yml")
    raw_code = code_m.group(1)
    try:
        code = int(raw_code, 0)
    except ValueError:
        code = int(raw_code)
    name = name_m.group(1).strip().strip("'\"")
    return code, name


def resolve_label_string_name(project: Path) -> str:
    """
    找出手機桌面實際顯示的那個字串資源叫什麼名字。

    多數 App 會用 Android 的慣例命名 app_name，但也有 App（例如把顯示名稱
    另外取名成 launcher_name 之類的自訂名稱）不遵循這個慣例。這裡直接去讀
    AndroidManifest.xml 裡 <application android:label="..."> 實際引用的是
    哪一個字串資源，而不是預先假設一定叫 app_name，這樣才能對應到 App 真正
    使用的命名。

    如果 android:label 不是 @string/ 形式的引用（例如直接寫死文字），或者
    manifest 裡根本沒有這個屬性，就回退使用 "app_name" 這個最常見的慣例
    名稱，維持對標準命名 App 的原有行為不變。
    """
    manifest = project / "AndroidManifest.xml"
    if manifest.exists():
        text = manifest.read_text(encoding="utf-8")
        m = re.search(r"<application\b[^>]*\bandroid:label=\"@string/([^\"]+)\"", text)
        if m:
            return m.group(1)
    return "app_name"


def parse_default_app_name(project: Path) -> str:
    label_name = resolve_label_string_name(project)
    # 仍然優先嘗試慣例名稱 app_name 作為次要來源：如果 manifest 解析不出
    # 具體引用（例如標籤是寫死文字而非字串資源），至少保留原本找 app_name
    # 的行為，而不是直接放棄。
    names_to_try = [label_name] if label_name == "app_name" else [label_name, "app_name"]
    for name in names_to_try:
        pattern = re.compile(rf'<string\s+name="{re.escape(name)}"[^>]*>(.*?)</string>', re.DOTALL)
        for candidate in [project / "res/values/strings.xml", *sorted((project / "res").glob("values*/strings.xml"))]:
            if not candidate.exists():
                continue
            text = candidate.read_text(encoding="utf-8")
            m = pattern.search(text)
            if m:
                value = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                if value:
                    return value
    manifest = project / "AndroidManifest.xml"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        match = re.search(r'<application\b[^>]*\bandroid:label="([^"\n]*)"', text)
        if match and match.group(1) and not match.group(1).startswith("@"):
            return html.unescape(match.group(1))
    return "App"


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    try:
        if path.stat().st_size > 8 * 1024 * 1024:
            return False
        sample = path.read_bytes()[:4096]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def replace_in_tree(root: Path, replacements: Sequence[tuple[str, str]]) -> dict[str, int]:
    counts = {old: 0 for old, _ in replacements}
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or not is_probably_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new_text = text
        for old, new in replacements:
            occurrences = new_text.count(old)
            if occurrences:
                new_text = new_text.replace(old, new)
                counts[old] += occurrences
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    return counts


def relocate_smali_package(project: Path, old_package: str, new_package: str) -> list[str]:
    old_rel = Path(*old_package.split("."))
    new_rel = Path(*new_package.split("."))
    moved: list[str] = []
    for smali_root in sorted(p for p in project.iterdir() if p.is_dir() and p.name.startswith("smali")):
        source = smali_root / old_rel
        if not source.exists():
            continue
        with tempfile.TemporaryDirectory(prefix="apkclone-relocate-") as tmp:
            staged = Path(tmp) / "pkg"
            shutil.move(str(source), str(staged))
            destination = smali_root / new_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise CloneError(f"Destination smali package already exists: {destination}")
            shutil.move(str(staged), str(destination))
        # Clean empty old package parent directories without crossing smali root.
        parent = source.parent
        while parent != smali_root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        moved.append(f"{smali_root.name}/{old_rel} -> {smali_root.name}/{new_rel}")
    return moved


def update_all_app_names(project: Path, app_name: str) -> int:
    count = 0
    label_name = resolve_label_string_name(project)
    # label_name 是 manifest 裡 android:label 實際引用的字串資源名稱（例如
    # app_name 或 launcher_name 等自訂名稱）。同時保留對 app_name 本身的
    # 更新，因為就算它不是桌面顯示名稱的來源，它仍是 Android 生態系裡最常
    # 被其他地方（例如系統設定裡的 App 名稱、部分第三方元件）引用的慣例
    # 資源，一併更新可以避免其他地方顯示不一致的舊名字。
    names_to_update = {label_name, "app_name"}
    res = project / "res"
    for name in names_to_update:
        pattern = re.compile(rf'(<string\s+name="{re.escape(name)}"[^>]*>)(.*?)(</string>)', re.DOTALL)
        for strings in sorted(res.glob("values*/strings.xml")):
            text = strings.read_text(encoding="utf-8")
            new_text, n = pattern.subn(lambda m: m.group(1) + escape_xml_text(app_name) + m.group(3), text, count=1)
            if n:
                strings.write_text(new_text, encoding="utf-8")
                count += 1
    if count == 0:
        manifest = project / "AndroidManifest.xml"
        text = manifest.read_text(encoding="utf-8")
        new_text, n = re.subn(r"(<application\b[^>]*\bandroid:label=)\"[^\"]*\"",
                              lambda m: m.group(1) + '"' + escape_xml_text(app_name) + '"', text, count=1)
        if n:
            manifest.write_text(new_text, encoding="utf-8")
            count = 1
    return count


def escape_xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def update_version(apktool_yml: Path, version_code: int, version_name: str) -> None:
    text = apktool_yml.read_text(encoding="utf-8")
    text, n_code = re.subn(r"(?m)^(\s*versionCode:\s*).*$", rf"\g<1>{version_code}", text, count=1)
    text, n_name = re.subn(r"(?m)^(\s*versionName:\s*).*$", rf"\g<1>{version_name}", text, count=1)
    if not n_code or not n_name:
        raise CloneError("Failed to update apktool.yml versionInfo")
    apktool_yml.write_text(text, encoding="utf-8")


def expand_template(template: str, *, number: int, app_name: str, package: str,
                    old_package: str, base_name: str, base_version_name: str) -> str:
    try:
        return template.format(
            n=number, number=number, name=app_name, package=package,
            old_package=old_package, base_name=base_name,
            base_version_name=base_version_name,
        )
    except KeyError as e:
        raise CloneError(f"Unknown template variable {e} in: {template}") from e


def parse_replace_arg(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise CloneError(f"--replace must be OLD=NEW_TEMPLATE: {raw}")
    old, new = raw.split("=", 1)
    if not old:
        raise CloneError("--replace OLD cannot be empty")
    return old, new


def verify_no_stale_package(project: Path, old_package: str, new_package: str) -> list[str]:
    warnings: list[str] = []
    dot_pattern = re.compile(re.escape(old_package) + r"(?![A-Za-z0-9_])")
    slash_old = old_package.replace(".", "/")
    slash_pattern = re.compile(re.escape(slash_old) + r"(?![A-Za-z0-9_])")
    hits: list[str] = []
    for path in project.rglob("*"):
        if not path.is_file() or not is_probably_text(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if dot_pattern.search(text) or slash_pattern.search(text):
            hits.append(str(path.relative_to(project)))
            if len(hits) >= 20:
                break
    if hits:
        warnings.append("Possible stale package references: " + ", ".join(hits))
    for smali_root in (p for p in project.iterdir() if p.is_dir() and p.name.startswith("smali")):
        if (smali_root / Path(*old_package.split("."))).exists():
            warnings.append(f"Old smali package directory remains under {smali_root.name}")
    return warnings


def inspect_native_package_risk(project: Path, old_package: str) -> list[str]:
    warnings: list[str] = []
    needles = [old_package.encode(), old_package.replace(".", "/").encode(), old_package.replace(".", "_").encode()]
    for so in project.rglob("*.so"):
        try:
            data = so.read_bytes()
        except OSError:
            continue
        if any(n in data for n in needles):
            warnings.append(f"Native library may contain package-bound JNI strings: {so.relative_to(project)}")
    return warnings


def ensure_zip_ok(apk: Path) -> None:
    with zipfile.ZipFile(apk) as zf:
        bad = zf.testzip()
        if bad:
            raise CloneError(f"Corrupt ZIP entry in {apk.name}: {bad}")


def extract_badging(aapt2: Path | None, apk: Path) -> str:
    if not aapt2:
        return "aapt2 unavailable"
    result = run([aapt2, "dump", "badging", apk], check=False)
    if result.returncode != 0:
        return "aapt2 badging failed: " + (result.stdout or "").strip()[-2000:]
    lines = [line for line in (result.stdout or "").splitlines() if line.startswith(("package:", "application-label", "sdkVersion", "targetSdkVersion"))]
    return "\n".join(lines[:20])


def generate_keystore(keytool: Path, keystore: Path, alias: str, storepass: str, keypass: str) -> None:
    keystore.parent.mkdir(parents=True, exist_ok=True)
    run([
        keytool, "-genkeypair", "-v", "-keystore", keystore,
        "-alias", alias, "-keyalg", "RSA", "-keysize", "2048",
        "-validity", "10000", "-storepass", storepass, "-keypass", keypass,
        "-dname", "CN=APK Clone Test, OU=Local, O=Local, L=Unknown, ST=Unknown, C=US",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create independently installable APK clones using apktool.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--apk", required=True, help="Input APK")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument("--numbers", default="1,2,3,4", help="Comma-separated clone numbers")
    parser.add_argument("--name-template", default="{base_name}{n}", help="Launcher name template")
    parser.add_argument("--package-template", default="{old_package}.clone{n}", help="Package template")
    parser.add_argument("--version-name-template", default="{base_version_name}-clone{n}")
    parser.add_argument("--version-code-base", type=int, help="First clone versionCode; default base+1")
    parser.add_argument("--filename-template", default="{name}.apk")
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW_TEMPLATE",
                        help="Additional text replacement; may use {n}, {package}, {name}")
    parser.add_argument("--apktool", help="apktool executable or apktool .jar")
    parser.add_argument("--android-sdk", help="Android SDK root; defaults to ANDROID_SDK_ROOT")
    parser.add_argument("--zipalign", help="zipalign executable")
    parser.add_argument("--apksigner", help="apksigner executable")
    parser.add_argument("--aapt2", help="aapt2 executable")
    parser.add_argument("--keystore", help="Signing keystore; generated in output dir if omitted")
    parser.add_argument("--ks-alias", default="apkclone")
    parser.add_argument("--ks-pass", default="android")
    parser.add_argument("--key-pass", default="android")
    parser.add_argument("--keep-work", action="store_true", help="Keep decoded clone projects")
    args = parser.parse_args()

    apk = Path(args.apk).expanduser().resolve()
    if not apk.is_file():
        raise CloneError(f"Input APK not found: {apk}")
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work_root = out_dir / "work"
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    java = find_executable(None, "java")
    keytool = find_executable(None, "keytool")
    sdk_env = args.android_sdk or os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    sdk_root = Path(sdk_env).expanduser().resolve() if sdk_env else None
    apktool = Path(args.apktool).expanduser().resolve() if args.apktool else None
    if not apktool:
        found = shutil.which("apktool")
        if found:
            apktool = Path(found).resolve()
        else:
            bundled = Path(__file__).resolve().parent / "apktool-cli-2.11.1.jar"
            if bundled.exists():
                apktool = bundled
            else:
                raise CloneError("apktool not found; use --apktool or place apktool-cli-2.11.1.jar beside this script")
    zipalign = find_build_tool(args.zipalign, sdk_root, "zipalign")
    apksigner = find_build_tool(args.apksigner, sdk_root, "apksigner")
    try:
        aapt2 = find_build_tool(args.aapt2, sdk_root, "aapt2")
    except CloneError:
        aapt2 = None

    keystore = Path(args.keystore).expanduser().resolve() if args.keystore else out_dir / "apk-clone-test.jks"
    if not keystore.exists():
        print(f"WARNING: generating a test keystore at {keystore}; preserve it for future updates.", file=sys.stderr)
        generate_keystore(keytool, keystore, args.ks_alias, args.ks_pass, args.key_pass)

    base_project = work_root / "base"
    decode_apk(apk, base_project, apktool, java)
    old_package = parse_manifest_package(base_project / "AndroidManifest.xml")
    base_version_code, base_version_name = parse_apktool_version(base_project / "apktool.yml")
    base_name = parse_default_app_name(base_project)

    numbers = [int(x.strip()) for x in args.numbers.split(",") if x.strip()]
    if not numbers or len(set(numbers)) != len(numbers):
        raise CloneError("--numbers must contain unique integers")
    extra_templates = [parse_replace_arg(x) for x in args.replace]

    specs: list[CloneSpec] = []
    for pos, number in enumerate(numbers):
        package_name = expand_template(args.package_template, number=number, app_name="", package="",
                                       old_package=old_package, base_name=base_name,
                                       base_version_name=base_version_name)
        if not PACKAGE_RE.fullmatch(package_name):
            raise CloneError(f"Invalid package name generated for clone {number}: {package_name}")
        app_name = expand_template(args.name_template, number=number, app_name="", package=package_name,
                                   old_package=old_package, base_name=base_name,
                                   base_version_name=base_version_name)
        version_code = (args.version_code_base if args.version_code_base is not None else base_version_code + 1) + pos
        version_name = expand_template(args.version_name_template, number=number, app_name=app_name,
                                       package=package_name, old_package=old_package,
                                       base_name=base_name, base_version_name=base_version_name)
        filename = expand_template(args.filename_template, number=number, app_name=app_name,
                                   package=package_name, old_package=old_package,
                                   base_name=base_name, base_version_name=base_version_name)
        filename = filename.replace(os.sep, "_")
        if not filename.lower().endswith(".apk"):
            filename += ".apk"
        specs.append(CloneSpec(number, app_name, package_name, version_code, version_name, filename))

    reports: list[CloneReport] = []
    for spec in specs:
        print(f"\n=== Clone {spec.number}: {spec.app_name} / {spec.package_name} ===", flush=True)
        project = work_root / f"clone-{spec.number}"
        shutil.copytree(base_project, project)

        dot_replacements: list[tuple[str, str]] = [(old_package, spec.package_name)]
        slash_replacements: list[tuple[str, str]] = [(old_package.replace(".", "/"), spec.package_name.replace(".", "/"))]
        extra_replacements: list[tuple[str, str]] = []
        for old, template in extra_templates:
            new = expand_template(template, number=spec.number, app_name=spec.app_name,
                                  package=spec.package_name, old_package=old_package,
                                  base_name=base_name, base_version_name=base_version_name)
            extra_replacements.append((old, new))
        counts = replace_in_tree(project, slash_replacements + dot_replacements + extra_replacements)
        moved = relocate_smali_package(project, old_package, spec.package_name)
        name_updates = update_all_app_names(project, spec.app_name)
        update_version(project / "apktool.yml", spec.version_code, spec.version_name)

        warnings = verify_no_stale_package(project, old_package, spec.package_name)
        warnings.extend(inspect_native_package_risk(project, old_package))
        if name_updates == 0:
            warnings.append("No app_name resource or manifest label was updated")

        unsigned = work_root / f"clone-{spec.number}-unsigned.apk"
        aligned = work_root / f"clone-{spec.number}-aligned.apk"
        final = out_dir / spec.output_apk
        build_apk(project, unsigned, apktool, java)
        run([zipalign, "-f", "4", unsigned, aligned])
        run([
            apksigner, "sign", "--v4-signing-enabled", "false",
            "--ks", keystore, "--ks-key-alias", args.ks_alias,
            "--ks-pass", f"pass:{args.ks_pass}", "--key-pass", f"pass:{args.key_pass}",
            "--out", final, aligned,
        ])
        sig = run([apksigner, "verify", "--verbose", "--print-certs", final]).stdout or ""
        run([zipalign, "-c", "-v", "4", final])
        ensure_zip_ok(final)
        badging = extract_badging(aapt2, final)
        if spec.package_name not in badging:
            warnings.append("aapt2 badging did not contain expected package name")

        report = CloneReport(
            spec=asdict(spec),
            base_package=old_package,
            base_version_code=base_version_code,
            base_version_name=base_version_name,
            replacements={old: new for old, new in dot_replacements + slash_replacements + extra_replacements},
            package_refs_replaced=counts.get(old_package, 0),
            slash_refs_replaced=counts.get(old_package.replace(".", "/"), 0),
            app_name_files_updated=name_updates,
            relocated_smali_roots=moved,
            apk_sha256=sha256_file(final),
            apk_size=final.stat().st_size,
            aapt2_badging=badging,
            signature_summary="\n".join(line for line in sig.splitlines() if "Signer #1 certificate" in line or "Verified using" in line),
            warnings=warnings,
        )
        reports.append(report)
        (out_dir / f"{final.stem}.report.json").write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    summary = {
        "tool": "apk_clone_maker.py",
        "input_apk": str(apk),
        "input_sha256": sha256_file(apk),
        "base_package": old_package,
        "base_version_code": base_version_code,
        "base_version_name": base_version_name,
        "base_app_name": base_name,
        "clones": [asdict(r) for r in reports],
    }
    (out_dir / "clone-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.keep_work:
        shutil.rmtree(work_root)
    print("\nCompleted clones:")
    for report in reports:
        spec = report.spec
        print(f"- {spec['app_name']}: {spec['package_name']} -> {spec['output_apk']} [{report.apk_sha256[:16]}]")
        for warning in report.warnings:
            print(f"  WARNING: {warning}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CloneError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
