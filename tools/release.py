#!/usr/bin/env python3
"""Rilis versi baru ke website LF ITS Robotics.

Menyalin hasil build dari repo firmware ke folder releases/, menghitung MD5 +
ukuran, memperbarui manifest.json (5 versi firmware terakhir) dan
flash-manifest.json (ESP Web Tools). Jalankan dari mana saja:

    python3 tools/release.py --notes "Robot belok lebih tepat. Blok baru: putar X derajat."

Opsi:
    --repo PATH      repo firmware (default ~/Projects/LF-ITSRobotics)
    --notes TEKS     catatan perubahan untuk siswa (default: subjek commit "Firmware X: ...")
    --no-firmware    jangan rilis firmware (hanya web UI / APK)
    --no-webui       jangan rilis web UI
    --no-apk         jangan cek APK
    --keep N         jumlah versi firmware yang disimpan (default 5)
"""
import argparse, datetime, hashlib, json, os, re, shutil, struct, subprocess, sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
MANIFEST = SITE / "manifest.json"
FLASH_MANIFEST = SITE / "flash-manifest.json"
APP_OFFSET = 0x10000  # app0 di tabel partisi ESP32 standar
# Bagian lain yang ikut di-flash lewat USB (ESP32-S3): robot bekas Arduino IDE
# bisa punya bootloader/tabel partisi lain, dan app saja tidak akan boot.
BOOT_PARTS = [  # (kunci, offset, nama file di .pio/build/robot)
    ("bootloader", 0x0, "bootloader.bin"),
    ("partitions", 0x8000, "partitions.bin"),
    ("boot_app0", 0xE000, None),  # dari paket framework, bukan folder build
]


def md5(p: Path) -> str:
    h = hashlib.md5()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_version(repo: Path) -> str:
    cfg = (repo / "src/config.h").read_text(encoding="utf-8")
    m = re.search(r'FIRMWARE_VERSION\[\]\s*=\s*"([^"]+)"', cfg)
    if not m:
        sys.exit("FIRMWARE_VERSION tidak ditemukan di src/config.h")
    return m.group(1)


def read_apk_version(repo: Path) -> str:
    g = repo / "web-remote/android/app/build.gradle"
    if g.exists():
        m = re.search(r'versionName\s+"([^"]+)"', g.read_text())
        if m:
            return m.group(1)
    return "0"


def check_esp32s3_image(p: Path):
    with p.open("rb") as f:
        hdr = f.read(24)
    if len(hdr) < 24 or hdr[0] != 0xE9:
        sys.exit(f"{p}: bukan image ESP32 (magic 0xE9 tidak ada)")
    chip_id = struct.unpack_from("<H", hdr, 12)[0]
    if chip_id != 9:  # ESP32-S3
        sys.exit(f"{p}: chip id {chip_id}, bukan ESP32-S3 (9)")


def find_boot_app0() -> Path:
    for base in (Path.home() / ".platformio/packages").glob("framework-arduinoespressif32*"):
        p = base / "tools/partitions/boot_app0.bin"
        if p.exists():
            return p
    sys.exit("boot_app0.bin tidak ditemukan di ~/.platformio/packages/framework-arduinoespressif32*")


def default_notes(repo: Path, version: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--format=%s", f"--grep=Firmware {version}"],
            capture_output=True, text=True, check=True).stdout.strip().splitlines()
    except Exception:
        return ""
    if not out:
        return ""
    return out[0].split(":", 1)[-1].strip().capitalize()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {"product": "lf-advanced", "name": "Line Follower ADVANCED",
            "latest": None, "versions": [], "webui": None, "remote": None}


def copy(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    os.chmod(dst, 0o644)
    print(f"  {dst.relative_to(SITE)}  {dst.stat().st_size/1024:.0f} KB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.expanduser("~/Projects/LF-ITSRobotics"))
    ap.add_argument("--notes")
    ap.add_argument("--no-firmware", action="store_true")
    ap.add_argument("--no-webui", action="store_true")
    ap.add_argument("--no-apk", action="store_true")
    ap.add_argument("--keep", type=int, default=5)
    a = ap.parse_args()

    repo = Path(a.repo).expanduser().resolve()
    version = read_version(repo)
    today = datetime.date.today().isoformat()
    m = load_manifest()
    print(f"Firmware {version} dari {repo}")

    # --- firmware ---
    if not a.no_firmware:
        src = repo / ".pio/build/robot/firmware.bin"
        if not src.exists():
            sys.exit(f"{src} tidak ada. Build dulu: pio run -e robot")
        check_esp32s3_image(src)
        rel = f"releases/firmware/lf-advanced-{version}.bin"
        copy(src, SITE / rel)
        boot = {}
        for key, offset, name in BOOT_PARTS:
            bsrc = repo / ".pio/build/robot" / name if name else find_boot_app0()
            if not bsrc.exists():
                sys.exit(f"{bsrc} tidak ada. Build dulu: pio run -e robot")
            brel = f"releases/firmware/lf-advanced-{version}-{key}.bin"
            copy(bsrc, SITE / brel)
            boot[key] = {"file": brel, "offset": offset}
        old = next((v for v in m["versions"] if v["version"] == version), {})
        entry = {
            **old,
            "version": version, "date": today, "hw": ["A"],
            "file": rel, "size": (SITE / rel).stat().st_size, "md5": md5(SITE / rel),
            "bc_version": 1,
            "notes": a.notes or old.get("notes") or default_notes(repo, version),
            "boot": boot,
        }
        m["versions"] = [v for v in m["versions"] if v["version"] != version]
        m["versions"].insert(0, entry)
        m["latest"] = version

    # --- web UI (dinamai mengikuti versi firmware, sesuai rencana_update_customer.md) ---
    if not a.no_webui:
        src = repo / "web-ui/dist/lf-blockly.html"
        if not src.exists():
            sys.exit(f"{src} tidak ada. Build dulu: cd web-ui && npm run build")
        rel = f"releases/webui/lf-blockly-{version}.html"
        copy(src, SITE / rel)
        m["webui"] = {"version": version, "date": today, "file": rel,
                      "size": (SITE / rel).stat().st_size, "md5": md5(SITE / rel)}
        for v in m["versions"]:
            if v["version"] == version:
                v["webui"] = rel

    # --- APK remote: hanya bila berubah ---
    if not a.no_apk:
        src = repo / "web-remote/LF-Remote.apk"
        if src.exists():
            h = md5(src)
            if not m.get("remote") or m["remote"].get("md5") != h:
                ver = read_apk_version(repo)
                rel = f"releases/remote/LF-Remote-{ver}.apk"
                old = (m.get("remote") or {}).get("file")
                copy(src, SITE / rel)
                m["remote"] = {"version": ver, "date": today, "file": rel,
                               "size": (SITE / rel).stat().st_size, "md5": h}
                if old and old != rel and (SITE / old).exists():
                    (SITE / old).unlink()
            else:
                print("  APK tidak berubah, dilewati")

    # --- pangkas ke N versi, hapus file yang tak dirujuk ---
    m["versions"] = m["versions"][: a.keep]
    keep_files = {v["file"] for v in m["versions"]} | {v.get("webui") for v in m["versions"]}
    for v in m["versions"]:
        keep_files |= {b["file"] for b in v.get("boot", {}).values()}
    if m.get("webui"):
        keep_files.add(m["webui"]["file"])
    for d in ("releases/firmware", "releases/webui"):
        for f in (SITE / d).glob("*"):
            if str(f.relative_to(SITE)) not in keep_files:
                print(f"  hapus {f.relative_to(SITE)} (lebih dari {a.keep} versi)")
                f.unlink()

    m["updated"] = today
    MANIFEST.write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # --- manifest ESP Web Tools (jalur darurat lewat USB) ---
    if m["versions"]:
        latest = m["versions"][0]
        boot = latest.get("boot", {})
        parts = [{"path": b["file"], "offset": b["offset"]}
                 for b in sorted(boot.values(), key=lambda b: b["offset"])]
        if not parts:
            print("  PERINGATAN: versi terbaru tanpa bootloader/partisi, flasher USB hanya menulis app")
        parts.append({"path": latest["file"], "offset": APP_OFFSET})
        FLASH_MANIFEST.write_text(json.dumps({
            "name": m["name"], "version": latest["version"],
            "new_install_prompt_erase": False,
            "builds": [{"chipFamily": "ESP32-S3", "parts": parts}],
        }, indent=2) + "\n", encoding="utf-8")

    print(f"manifest.json: latest {m['latest']}, {len(m['versions'])} versi firmware")
    print("Lanjutkan: git add -A && git commit -m \"Rilis firmware", version + "\" && git push")


if __name__ == "__main__":
    main()
