# LF ITS Robotics — website Line Follower ADVANCED

Situs statis (GitHub Pages) untuk pengguna robot: fitur, spesifikasi, unduhan
(web app, firmware, APK remote), cara update, panduan singkat.

Tayang di: https://ismarintan98.github.io/LF_ITS-Share/

## Isi

| File | Isi |
|---|---|
| `index.html` | Halaman utama. Bagian Unduhan dibuat otomatis dari `manifest.json` |
| `flash.html` | Flasher USB darurat (ESP Web Tools), membaca `flash-manifest.json` |
| `manifest.json` | Daftar versi: 5 firmware terakhir, web UI, APK. Format sesuai `docs/rencana_update_customer.md` di repo firmware; nanti dibaca juga oleh web app untuk "Versi baru tersedia" |
| `flash-manifest.json` | Manifest ESP Web Tools (firmware terbaru, offset 0x10000, ESP32-S3) |
| `releases/firmware/` | `lf-advanced-<versi>.bin` (maks 5) |
| `releases/webui/` | `lf-blockly-<versi>.html` (dinamai mengikuti versi firmware) |
| `releases/remote/` | `LF-Remote-<versi>.apk` |
| `assets/` | Logo ITS, model 3D `robot.glb` (dari `web-ui/src/assets`) |
| `tools/release.py` | Skrip rilis (lihat di bawah) |

## Merilis versi baru

Di repo firmware (`~/Projects/LF-ITSRobotics`): naikkan `FIRMWARE_VERSION`
di `src/config.h`, build firmware dan web UI:

```sh
pio run -e robot
cd web-ui && npm run build && cd ..
# APK (bila berubah): lihat web-remote/README.md, hasil disalin ke web-remote/LF-Remote.apk
```

Lalu di repo ini:

```sh
python3 tools/release.py --notes "Catatan untuk siswa, bahasa sederhana."
git add -A && git commit -m "Rilis firmware 0.20.0" && git push
```

Skrip menyalin `.pio/build/robot/firmware.bin` → `releases/firmware/`,
`web-ui/dist/lf-blockly.html` → `releases/webui/`, APK bila MD5-nya berubah,
memeriksa header image ESP32-S3, menghitung MD5 + ukuran, menaruh versi baru di
atas `manifest.json`, membuang versi ke-6 dan seterusnya (file ikut dihapus),
dan menulis ulang `flash-manifest.json`. Tanpa `--notes`, catatan diambil dari
subjek commit `Firmware <versi>: ...`. Opsi lain: `--no-firmware`, `--no-webui`,
`--no-apk`, `--keep N`, `--repo PATH`.

Mengubah teks halaman: edit `index.html` langsung (Tailwind lewat CDN, tanpa
build). Mengubah catatan versi lama: edit `manifest.json`.

## Pratinjau lokal

`fetch('manifest.json')` tidak jalan dari `file://`, jadi:

```sh
python3 -m http.server 8000
# buka http://localhost:8000/
```

Flasher USB butuh HTTPS atau `localhost`.

## Deploy pertama kali

```sh
git init -b main && git add -A && git commit -m "Website LF ITS Robotics"
gh repo create ismarintan98/LF_ITS-Share --public --source . --push
gh api -X POST repos/ismarintan98/LF_ITS-Share/pages \
  -f build_type=legacy -f 'source[branch]=main' -f 'source[path]=/'
```

Situs tayang 1–2 menit kemudian. GitHub Pages otomatis mengirim header CORS
(`Access-Control-Allow-Origin: *`), jadi web app bisa membaca `manifest.json`
dan mengunduh `.bin` langsung dari situs ini.
