# am-finder

Temukan **link preset Alight Motion (AM)** dari sebuah video TikTok.

Preset AM sering "tenggelam":
- link ditaruh di **deskripsi** tapi tak bisa disalin,
- atau disembunyikan di **komentar** yang jumlahnya ribuan,
- atau diarahkan "link di bio" / "cek komentar pin".

`am-finder` menerima satu URL video TikTok, lalu memindai **deskripsi**, **bio kreator**, dan **komentar** (yang disematkan diprioritaskan) untuk menemukan dan menilai kandidat link preset.

## Fitur

- 🔎 Ekstraksi link cerdas: mengenali Google Drive, MediaFire, Mega, Dropbox, link pendek, Telegram, dll.
- 🧠 **Skor kepercayaan** tiap link + alasan penilaiannya.
- 📌 Deteksi **komentar disematkan** dan komentar milik kreator.
- ⚠️ Deteksi link "tidak langsung" (mis. "link di bio").
- 🖥️ **Web app** tanpa dependensi + **CLI**.
- 🧩 Arsitektur **pluggable** — mudah menambah penyedia data TikTok lain.

## Menjalankan

Butuh **Python 3.10+**. Tidak ada dependensi eksternal (murni standard library).

### Web app (lokal)

```bash
python3 -m amfinder.server --port 8000
```

Lalu buka http://127.0.0.1:8000 dan tempel URL video TikTok.

### Sebagai layanan (start/stop/restart)

```bash
./run.sh start     # jalankan di background (port 8000, bisa diakses LAN)
./run.sh status
./run.sh logs
./run.sh stop
./run.sh restart
```

Ganti port/host: `PORT=9000 HOST=127.0.0.1 ./run.sh restart`.

### Deploy ke Vercel

Proyek sudah menyertakan adaptor WSGI (`index.py`) dan `vercel.json` sehingga
kode inti yang sama bisa langsung di-deploy.

```bash
# sekali: pasang CLI Vercel
npm i -g vercel

# deploy preview
vercel

# deploy produksi
vercel --prod
```

Atau hubungkan repositori GitHub ke Vercel — Vercel akan otomatis mendeteksi
entrypoint `index:app` dari `pyproject.toml`. Tidak perlu konfigurasi tambahan.

### CLI

```bash
python3 -m amfinder.cli "https://www.tiktok.com/@user/video/123..."
python3 -m amfinder.cli "<url>" --limit 150       # pindai lebih banyak komentar
python3 -m amfinder.cli "<url>" --json            # keluarkan JSON
```

### Test

```bash
python3 -m amfinder.tests -v
```

## Cara kerja

```
URL TikTok
    │
    ▼
[tiktok.py]  ambil video + komentar + bio   (lewat penyedia pluggable, mis. tikwm)
    │
    ▼
[extractor.py]  temukan & skor kandidat link dari tiap teks
    │
    ▼
[finder.py]  gabungkan, urutkan, bungkus jadi FindResult
    │
    ▼
[server.py / cli.py]  tampilkan ke pengguna
```

## Skor link

| Sinyal | Poin |
|---|---|
| Host penyimpanan file (Drive, MediaFire, Mega, …) | +40 |
| Referensi langsung Alight Motion (`alightcreative`, `.am`, `.xml`) | +35 |
| Ekstensi berkas preset (`.xml`, `.am`, `.zip`, …) | +25 |
| Kata kunci "preset" di sekitar link | +15 |
| Teks sumber membahas preset | +5 |
| Link pendek/agregator (bit.ly, linktree, t.me, …) | −5 |
| Diarahkan ke bio/komentar (tidak langsung) | −10 |

## Menambah penyedia TikTok

TikTok tak punya API publik resmi; data diambil lewat penyedia pihak ketiga
yang bisa berubah/limit kapan saja. Saat ini tersedia **tikwm** (tanpa login,
limit ~1 permintaan/detik; sudah ditangani dengan throttle + retry otomatis).

Untuk menambah penyedia, buat kelas di `amfinder/tiktok.py` dengan metode
`fetch_video(url) -> VideoInfo` dan `fetch_comments(url, limit) -> list[Comment]`,
lalu daftarkan di list `PROVIDERS`.

## Batasan

- Link yang **hanya muncul di dalam video** (teks di layar) belum dibaca
  otomatis — perlu OCR (rencana pengembangan berikutnya).
- Sangat bergantung pada ketersediaan penyedia pihak ketiga.
- Cakupan komentar dibatasi `--limit` (default 100) karena keterbatasan laju API.

## Struktur

```
am-finder/
├── amfinder/
│   ├── __init__.py
│   ├── extractor.py    # temukan & skor link preset
│   ├── tiktok.py       # penyedia data TikTok (pluggable)
│   ├── finder.py       # orkestrasi
│   ├── server.py       # web server lokal (stdlib)
│   ├── cli.py          # antarmuka terminal
│   ├── tests.py        # unit test
│   └── static/index.html
├── index.py            # entrypoint WSGI untuk Vercel
├── vercel.json         # konfigurasi deploy Vercel
├── pyproject.toml      # metadata + entrypoint (index:app)
├── run.sh              # kelola layanan lokal (start/stop/restart)
├── .python-version     # versi Python untuk Vercel (3.13)
└── README.md
```