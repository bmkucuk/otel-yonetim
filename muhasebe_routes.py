#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Muhasebe modülü — Flask route'ları"""
from datetime import date
from flask import Blueprint, render_template, request, jsonify, session, redirect
import muhasebe_db as mdb
from functools import wraps

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'):
            return redirect('/login')
        if session.get('role') != 'admin':
            return redirect('/')
        return f(*args, **kwargs)
    return decorated

muh = Blueprint('muhasebe', __name__)

AYLAR = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
         "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]

# ── Sayfalar ──────────────────────────────────────────────────────────────────

@muh.route('/muhasebe')
@admin_required
def muhasebe_index():
    return render_template('muhasebe/gosterge.html')

@muh.route('/muhasebe/yevmiye')
@admin_required
def muhasebe_yevmiye():
    return render_template('muhasebe/yevmiye.html')

@muh.route('/muhasebe/kasa-banka')
@login_required
def muhasebe_kasa():
    return render_template('muhasebe/kasa_banka.html')

@muh.route('/muhasebe/personel')
@admin_required
def muhasebe_personel():
    return render_template('muhasebe/personel.html')

@muh.route('/muhasebe/stok')
@login_required
def muhasebe_stok():
    return render_template('muhasebe/stok.html')

@muh.route('/muhasebe/demirbaş')
@login_required
def muhasebe_demirbaş():
    return render_template('muhasebe/demirbaş.html')

@muh.route('/muhasebe/vergi')
@admin_required
def muhasebe_vergi():
    return render_template('muhasebe/vergi.html')

@muh.route('/muhasebe/acente')
@login_required
def muhasebe_acente():
    return render_template('muhasebe/acente.html')

@muh.route('/muhasebe/gider-girisleri')
@login_required
def muhasebe_gider():
    return render_template('muhasebe/gider_girisleri.html')

@muh.route('/muhasebe/ortak-cari')
@admin_required
def muhasebe_ortak():
    return render_template('muhasebe/ortak_cari.html')

@muh.route('/muhasebe/mizan')
@admin_required
def muhasebe_mizan():
    return render_template('muhasebe/mizan.html')


# ── API — Gösterge ────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/gosterge')
def api_gosterge():
    yil = request.args.get('yil', date.today().year, type=int)

    # Yevmiyeden doğrudan oku
    conn = mdb.get_conn()
    def yev_sum(borc=None, alacak=None, tip=None):
        q = "SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=?"
        p = [yil]
        if borc:   q += " AND borc_hesap=?";   p.append(borc)
        if alacak: q += " AND alacak_hesap=?"; p.append(alacak)
        if tip:    q += " AND islem_tipi=?";   p.append(tip)
        return conn.execute(q, p).fetchone()[0] or 0

    leo_kon  = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND islem_tipi IN ('Konaklama Geliri','Kapora Yanması') AND otel='LEO'", (yil,)).fetchone()[0] or 0
    cv_kon   = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND islem_tipi IN ('Konaklama Geliri','Kapora Yanması') AND otel='CV'", (yil,)).fetchone()[0] or 0
    restoran = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND islem_tipi='Adisyon Geliri'", (yil,)).fetchone()[0] or 0
    # Tüm nakit girişleri (tahsilat + kapora)
    nakit    = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap='100'", (yil,)).fetchone()[0] or 0
    # Tüm banka girişleri (tahsilat + kapora)
    kk       = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap='102-1'", (yil,)).fetchone()[0] or 0
    havale   = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap='102-1' AND islem_tipi LIKE '%Havale%'", (yil,)).fetchone()[0] or 0
    kapora_gelen = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND islem_tipi='Kapora'", (yil,)).fetchone()[0] or 0
    kapora_yanan = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND islem_tipi='Kapora Yanması'", (yil,)).fetchone()[0] or 0
    kapora   = kapora_gelen - kapora_yanan
    # Açık bakiye = müşteri cari borç - alacak
    muc_borc  = conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap='120'", (yil,)).fetchone()[0] or 0
    muc_alacak= conn.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND alacak_hesap='120'", (yil,)).fetchone()[0] or 0
    acik = max(0, muc_borc - muc_alacak)
    conn.close()

    mizan = mdb.get_mizan_ozet(yil)
    maas  = mizan['maas']
    vergi = mizan['vergi']
    stok  = mizan['stok']
    dem   = mizan.get('demirbaş', 0)
    ortak_lk = mizan.get('ortak_lk', 0) or 0
    ortak_bt = mizan.get('ortak_bt', 0) or 0

    # Acente komisyon toplamı
    _ac = mdb.get_conn()
    acente_kom = _ac.execute(
        "SELECT COALESCE(SUM(komisyon_tl),0) FROM acente_cari WHERE strftime('%Y',tarih)=?",
        (str(yil),)).fetchone()[0] or 0
    _ac.close()

    toplam_gelir = leo_kon + cv_kon + restoran
    toplam_gider = maas + stok + vergi + acente_kom + ortak_lk + ortak_bt + dem
    net = toplam_gelir - toplam_gider

    # Aylık özet
    import sqlite3
    conn = mdb.get_conn()
    maas_ay = {row[0]: row[1] for row in conn.execute(
        "SELECT donem_ay, SUM(net_odeme) FROM personel_maas WHERE donem_yil=? GROUP BY donem_ay", (yil,)).fetchall()}
    vergi_ay = {row[0]: row[1] for row in conn.execute(
        "SELECT donem_ay, SUM(tutar) FROM vergi WHERE donem_yil=? AND durum='Ödendi' GROUP BY donem_ay", (yil,)).fetchall()}
    conn.close()

    # Aylık özet yevmiyeden
    conn2 = mdb.get_conn()
    aylik = []
    for i, ay_adi in enumerate(AYLAR):
        ay = i + 1
        leo  = conn2.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND ay=? AND islem_tipi IN ('Konaklama Geliri','Kapora Yanması') AND otel='LEO'", (yil,ay)).fetchone()[0] or 0
        cv_k = conn2.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND ay=? AND islem_tipi IN ('Konaklama Geliri','Kapora Yanması') AND otel='CV'", (yil,ay)).fetchone()[0] or 0
        rest = conn2.execute("SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND ay=? AND islem_tipi='Adisyon Geliri'", (yil,ay)).fetchone()[0] or 0
        gel  = leo + cv_k + rest
        pers = maas_ay.get(ay, 0) or 0
        vg   = vergi_ay.get(ay, 0) or 0
        n    = gel - pers - vg
        aylik.append({'ay': ay_adi, 'leo': leo, 'cv': cv_k, 'rest': rest,
                      'gel': gel, 'pers': pers, 'vergi': vg, 'net': n})

    conn2.close()
    return jsonify({
        'kartlar': {
            'leo_kon': leo_kon, 'cv_kon': cv_kon, 'restoran': restoran,
            'nakit': nakit, 'kk': kk, 'havale': havale,
            'tahsilat': nakit + kk + havale, 'acik': acik, 'kapora': kapora,
            'maas': maas, 'stok': stok, 'dem': dem, 'vergi': vergi, 'acente_kom': acente_kom,
            'ortak_lk': ortak_lk, 'ortak_bt': ortak_bt,
            'toplam_gelir': toplam_gelir, 'toplam_gider': toplam_gider, 'net': net,
        },
        'aylik': aylik,
    })


# ── API — Yevmiye ─────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/yevmiye')
def api_yevmiye():
    yil = request.args.get('yil', date.today().year, type=int)
    ay  = request.args.get('ay', 0, type=int) or None
    q   = request.args.get('q', '')
    rows = mdb.get_yevmiye(yil, ay)
    if q:
        rows = [r for r in rows if any(q.lower() in str(v).lower() for v in r.values())]
    return jsonify(rows)

@muh.route('/api/muhasebe/yevmiye/ekle', methods=['POST'])
def api_yevmiye_ekle():
    try:
        d = request.get_json()
        mdb.ekle_yevmiye(**d)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/yevmiye/sil', methods=['POST'])
def api_yevmiye_sil():
    try:
        import re as _re, sqlite3 as _sq
        d = request.get_json()
        yev_id = int(d['id'])
        conn = mdb.get_conn()
        yev = conn.execute(
            "SELECT kaynak_tablo, kaynak_id, islem_tipi, tutar, aciklama FROM yevmiye WHERE id=?",
            (yev_id,)).fetchone()
        if yev:
            tablo, kid, islem, tutar, aciklama = yev[0], yev[1], yev[2] or '', yev[3] or 0, yev[4] or ''
            guvenli = ['stok', 'demirbaş', 'personel_maas', 'acente_cari', 'vergi', 'ortak_cari']
            if tablo and kid and tablo in guvenli:
                conn.execute(f'DELETE FROM "{tablo}" WHERE id=?', (kid,))

            m = _re.search(r'Föy#(\d+)', aciklama)
            foy_no = int(m.group(1)) if m else None

            if 'Tahsilat' in islem and tutar > 0 and foy_no:
                oc = _sq.connect('/data/otel.db')
                if 'Adisyon' in islem:
                    oc.execute('UPDATE rezervasyonlar SET adis_tahsilat=adis_tahsilat-?,adis_bakiye=adis_bakiye+? WHERE foy_no=?', (tutar, tutar, foy_no))
                    # Adisyon no varsa odendi/odenen_tutar güncelle
                    ma = _re.search(r'Adis#(\d+)', aciklama)
                    if ma:
                        adis_no = int(ma.group(1))
                        oc.execute('UPDATE adisyonlar SET odendi=0, odenen_tutar=MAX(0,odenen_tutar-?) WHERE adisyon_no=?', (tutar, adis_no))
                        oc.execute('DELETE FROM adisyon_odemeler WHERE adisyon_no=? AND tutar=? ORDER BY id DESC LIMIT 1', (adis_no, tutar))
                else:
                    oc.execute('UPDATE rezervasyonlar SET rez_tahsilat=rez_tahsilat-?,rez_bakiye=rez_bakiye+? WHERE foy_no=?', (tutar, tutar, foy_no))
                oc.commit(); oc.close()

            elif islem == 'Adisyon Geliri' and tutar > 0 and foy_no:
                # Adisyon geliri silinince adisyon tablosunu güncelle
                oc = _sq.connect('/data/otel.db')
                oc.execute('UPDATE rezervasyonlar SET adisyon=MAX(0,adisyon-?), adis_bakiye=MAX(0,adis_bakiye-?) WHERE foy_no=?', (tutar, tutar, foy_no))
                ma = _re.search(r'Adis#(\d+)', aciklama)
                if ma:
                    adis_no = int(ma.group(1))
                    oc.execute('DELETE FROM adisyonlar WHERE adisyon_no=?', (adis_no,))
                oc.commit(); oc.close()

            elif islem == 'Konaklama Geliri' and tutar > 0 and foy_no:
                oc = _sq.connect('/data/otel.db')
                oc.execute('DELETE FROM rezervasyonlar WHERE foy_no=?', (foy_no,))
                oc.execute('DELETE FROM adisyonlar WHERE foy_no=?', (foy_no,))
                oc.execute('DELETE FROM adisyon_odemeler WHERE foy_no=?', (foy_no,))
                oc.commit(); oc.close()

            elif islem == 'Kapora' and tutar > 0 and foy_no:
                oc = _sq.connect('/data/otel.db')
                oc.execute('UPDATE rezervasyonlar SET kapora=MAX(0,kapora-?), rez_bakiye=rez_bakiye+? WHERE foy_no=?', (tutar, tutar, foy_no))
                oc.commit(); oc.close()

        conn.execute("DELETE FROM yevmiye WHERE id=?", (yev_id,))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/hesaplar')
def api_hesaplar():
    return jsonify(mdb.get_hesap_adlari())

@muh.route('/api/muhasebe/bankalar')
def api_bankalar():
    return jsonify(mdb.get_bankalar())


# ── API — Kasa/Banka ─────────────────────────────────────────────────────────

# Banka kodu → yevmiye hesap kodu eşleştirmesi
BANKA_HESAP = {
    'KASA': '100',
    'IS':   '102-1',
    'ZRH':  '102-2',
    'DNZ':  '102-3',
}

@muh.route('/api/muhasebe/kasa')
def api_kasa():
    yil = request.args.get('yil', date.today().year, type=int)
    hesap = request.args.get('hesap', '')
    bankalar = mdb.get_bankalar()
    conn = mdb.get_conn()
    bakiyeler = []
    for b in bankalar:
        h_kodu = BANKA_HESAP.get(b['kod'], b['kod'])
        # Aktif hesaplar: borç = giriş (para geldi), alacak = çıkış (para gitti)
        giris = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap=?",
            (yil, h_kodu)).fetchone()[0]
        cikis = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND alacak_hesap=?",
            (yil, h_kodu)).fetchone()[0]
        bakiyeler.append({'kod': b['kod'], 'ad': b['ad'], 'hesap_kodu': h_kodu,
                          'giris': giris, 'cikis': cikis, 'bakiye': giris - cikis})
    hareketler = []
    if hesap:
        h_kodu = BANKA_HESAP.get(hesap, hesap)
        rows = mdb.get_yevmiye(yil, hesap=h_kodu, order='ASC')
        # islem_tipi ekle
        for r in rows:
            r['islem_tipi'] = r.get('islem_tipi', '')
        bakiye = 0
        for r in rows:
            # Aktif hesap: borç hesabında görünüyorsa para girişi
            giris_mi = h_kodu in str(r['borc_hesap'])
            g = r['tutar'] if giris_mi else 0
            c = r['tutar'] if not giris_mi else 0
            bakiye += g - c
            hareketler.append({**r, 'giris': g, 'cikis': c, 'bakiye_kum': bakiye,
                               'karsi': r['borc_hesap'] if giris_mi else r['alacak_hesap']})
    conn.close()
    return jsonify({'bakiyeler': bakiyeler, 'hareketler': hareketler})


# ── API — Personel ────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/personel')
def api_personel():
    return jsonify(mdb.get_personel())

@muh.route('/api/muhasebe/personel/ekle', methods=['POST'])
def api_personel_ekle():
    try:
        d = request.get_json()
        mdb.ekle_personel(d['ad_soyad'], d.get('ise_giris'), d.get('gorev'),
                         float(d.get('net_maas', 0)), d.get('banka_iban', ''))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/maaslar')
def api_maaslar():
    yil = request.args.get('yil', date.today().year, type=int)
    conn = mdb.get_conn()
    rows = conn.execute("""
        SELECT pm.id, pm.tarih, p.ad_soyad, pm.donem_ay, pm.donem_yil,
               pm.net_odeme, COALESCE(pm.yol_parasi,0), COALESCE(pm.fazla_mesai,0),
               COALESCE(pm.avans_dusum,0), COALESCE(pm.izin_parasi,0), COALESCE(pm.gelmedi_gun,0),
               pm.odeme_banka, pm.otel, pm.aciklama, pm.personel_id
        FROM personel_maas pm JOIN personel p ON pm.personel_id=p.id
        WHERE pm.donem_yil=? ORDER BY pm.tarih ASC
    """, (yil,)).fetchall()
    conn.close()
    result = []
    for r in rows:
        result.append({
            'id': r[0], 'tarih': r[1], 'ad_soyad': r[2],
            'donem_ay': r[3], 'donem_yil': r[4],
            'net_odeme': r[5], 'yol_parasi': r[6], 'fazla_mesai': r[7],
            'avans_dusum': r[8], 'izin_parasi': r[9], 'gelmedi_gun': r[10],
            'odeme_banka': r[11], 'otel': r[12], 'aciklama': r[13],
            'personel_id': r[14]
        })
    return jsonify(result)

@muh.route('/api/muhasebe/maas/ekle', methods=['POST'])
def api_maas_ekle():
    try:
        d = request.get_json()
        mdb.ekle_maas(d['tarih'], int(d['personel_id']), int(d['donem_yil']),
                     int(d['donem_ay']), float(d['net_odeme']),
                     d.get('odeme_banka', ''), d.get('aciklama', ''), d.get('otel', 'GENEL'),
                     yol_parasi=float(d.get('yol_parasi', 0)),
                     fazla_mesai=float(d.get('fazla_mesai', 0)),
                     izin_parasi=float(d.get('izin_parasi', 0)),
                     gelmedi_gun=int(d.get('gelmedi_gun', 0)),
                     avans_dusum=float(d.get('avans_dusum', 0)))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Stok ────────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/stok')
def api_stok():
    yil = request.args.get('yil', date.today().year, type=int)
    kat = request.args.get('kat', '')
    conn = mdb.get_conn()
    q = "SELECT * FROM stok WHERE strftime('%Y',tarih)=?"
    params = [str(yil)]
    if kat: q += " AND kategori=?"; params.append(kat)
    q += " ORDER BY tarih ASC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return jsonify(rows)

@muh.route('/api/muhasebe/stok/ekle', methods=['POST'])
def api_stok_ekle():
    try:
        d = request.get_json()
        odeme_kod = BANKA_AD_KODU.get(d.get('odeme_hesap',''), d.get('odeme_hesap',''))
        mdb.ekle_stok(d['tarih'], d['aciklama'], float(d['tutar']),
                     d.get('kategori', 'Diğer'), d.get('belge_no', ''),
                     odeme_kod, bool(d.get('fatura_var', False)),
                     d.get('otel', 'GENEL'), d.get('not_', ''))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Demirbaş ───────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/demirbas')
def api_demirbas():
    yil = request.args.get('yil', date.today().year, type=int)
    conn = mdb.get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM [demirbaş] WHERE strftime('%Y',tarih)=? ORDER BY tarih ASC",
        (str(yil),)).fetchall()]
    conn.close()
    return jsonify(rows)

# Banka adı → hesap kodu
BANKA_AD_KODU = {
    'Kasa TL': '100', 'İş Bankası': '102-1',
    'Ziraat Bankası': '102-2', 'Deniz Bank': '102-3',
}
BANKA_HESAP_KODU = {'100': '100', '102-1': '102-1', '102-2': '102-2', '102-3': '102-3',
                    'KASA': '100', 'IS': '102-1', 'ZRH': '102-2', 'DNZ': '102-3'}


@muh.route('/api/muhasebe/demirbas/ekle', methods=['POST'])
def api_demirbas_ekle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        toplam = float(d.get('miktar', 1)) * float(d['birim_fiyat'])
        t = d['tarih']
        yil = int(t[:4]); ay = int(t[5:7])
        odeme_ad = d.get('odeme_hesap', '')
        odeme_kod = BANKA_AD_KODU.get(odeme_ad, odeme_ad)
        conn.execute("""
            INSERT INTO [demirbaş] (tarih,aciklama,miktar,birim_fiyat,toplam,odeme_hesap,fatura_no,otel,not_)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (t, d['aciklama'],
                float(d.get('miktar', 1)), float(d['birim_fiyat']), toplam,
                odeme_ad, d.get('fatura_no', ''),
                d.get('otel', 'GENEL'), d.get('not_', '')))
        # Yevmiye - aynı conn üzerinden
        dem_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if toplam > 0:
            conn.execute("""
                INSERT INTO yevmiye (tarih,yil,ay,belge_no,islem_tipi,borc_hesap,alacak_hesap,tutar,aciklama,otel,kaynak_tablo,kaynak_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (t, yil, ay, d.get('fatura_no',''), 'Demirbaş Alımı',
                    '255', odeme_kod or '100', toplam,
                    d['aciklama'], d.get('otel','GENEL'), 'demirbaş', dem_id))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/demirbas/sil', methods=['POST'])
def api_demirbas_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute('DELETE FROM [demirbaş] WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Vergi ────────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/vergi')
def api_vergi():
    yil = request.args.get('yil', date.today().year, type=int)
    conn = mdb.get_conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM vergi WHERE donem_yil=? ORDER BY donem_ay, vergi_turu", (yil,)).fetchall()]
    conn.close()
    for r in rows:
        if r.get('donem_ay') and 1 <= r['donem_ay'] <= 12:
            r['donem_ay_adi'] = AYLAR[r['donem_ay']-1]
    return jsonify(rows)

@muh.route('/api/muhasebe/vergi/ekle', methods=['POST'])
def api_vergi_ekle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("""
            INSERT INTO vergi (tarih,donem_yil,donem_ay,vergi_turu,matrah,tutar,odeme_banka,durum,aciklama)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (d.get('tarih'), int(d['donem_yil']), int(d['donem_ay']),
              d['vergi_turu'], float(d.get('matrah', 0)), float(d['tutar']),
              d.get('odeme_banka', ''), d.get('durum', 'Bekliyor'), d.get('aciklama', '')))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/vergi/onayla', methods=['POST'])
def api_vergi_onayla():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        tarih = d.get('tarih', date.today().isoformat())
        row = conn.execute("SELECT * FROM vergi WHERE id=?", (int(d['id']),)).fetchone()
        conn.execute("UPDATE vergi SET durum='Ödendi', tarih=? WHERE id=?",
                     (tarih, int(d['id'])))
        if row:
            import muhasebe_db as mdb2
            banka = row['odeme_banka'] or 'IS'
            banka_hesap = '100' if banka=='KASA' else '102-2' if banka=='ZRH' else '102-3' if banka=='DNZ' else '102-1'
            mdb2._yevmiye_ekle(conn, tarih, 'Vergi Ödemesi', '770', banka_hesap,
                               row['tutar'], f"{row['vergi_turu']} {row['donem_yil']}/{row['donem_ay']}", 'GENEL')
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Acente Cari ─────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/acente')
def api_acente():
    yil = request.args.get('yil', date.today().year, type=int)
    acente = request.args.get('acente', '')
    conn = mdb.get_conn()
    q = "SELECT * FROM acente_cari WHERE strftime('%Y',tarih)=?"
    params = [str(yil)]
    if acente: q += " AND acente_kod=?"; params.append(acente)
    q += " ORDER BY tarih ASC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    acenteler = [dict(r) for r in conn.execute("SELECT * FROM acenteler WHERE aktif=1").fetchall()]
    conn.close()
    return jsonify({'rows': rows, 'acenteler': acenteler})

@muh.route('/api/muhasebe/acente/ekle', methods=['POST'])
def api_acente_ekle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        komisyon = float(d.get('komisyon_tl', 0))
        gelen = float(d.get('gelen_odeme', 0))
        conn.execute("""
            INSERT INTO acente_cari
            (tarih,acente_kod,foy_no,rez_no,misafir,rez_tutari,komisyon_oran,komisyon_tl,gelen_odeme,otel)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (d['tarih'], d['acente_kod'], d.get('foy_no'), d.get('rez_no', ''),
              d.get('misafir', ''), float(d['rez_tutari']),
              float(d.get('komisyon_oran', 15)), komisyon,
              gelen, d.get('otel', 'LEO')))
        acente_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        if komisyon > 0:
            acente_hesap = '320-1'
            if d['acente_kod'] == 'EXP': acente_hesap = '320-2'
            elif d['acente_kod'] in ('JLY','TTS'): acente_hesap = '320-3'
            odeme_tipi = d.get('komisyon_odeme', 'Mahsup')
            if odeme_tipi == 'Banka':
                banka = d.get('odeme_banka', 'IS')
                banka_hesap = '102-2' if banka=='ZRH' else '102-3' if banka=='DNZ' else '102-1'
                mdb._yevmiye_ekle(conn, d['tarih'], 'Acente Komisyonu (Banka)',
                                  '730', banka_hesap, komisyon,
                                  f"{d['acente_kod']} komisyon", d.get('otel','LEO'),
                                  kaynak_tablo='acente_cari', kaynak_id=acente_id)
            else:
                mdb._yevmiye_ekle(conn, d['tarih'], 'Acente Komisyonu (Mahsup)',
                                  '730', acente_hesap, komisyon,
                                  f"{d['acente_kod']} komisyon mahsup", d.get('otel','LEO'),
                                  kaynak_tablo='acente_cari', kaynak_id=acente_id)
        if gelen > 0:
            banka = d.get('odeme_banka', 'IS')
            banka_hesap = '102-2' if banka=='ZRH' else '102-3' if banka=='DNZ' else '102-1'
            acente_hesap = '320-1'
            if d['acente_kod'] == 'EXP': acente_hesap = '320-2'
            elif d['acente_kod'] in ('JLY','TTS'): acente_hesap = '320-3'
            mdb._yevmiye_ekle(conn, d['tarih'], 'Acente Tahsilat',
                              banka_hesap, acente_hesap, gelen,
                              f"{d['acente_kod']} net ödeme", d.get('otel','LEO'),
                              kaynak_tablo='acente_cari', kaynak_id=acente_id)
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Ortak Cari ──────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/ortak')
def api_ortak():
    yil = request.args.get('yil', date.today().year, type=int)
    ortak = request.args.get('ortak', '')
    conn = mdb.get_conn()
    q = "SELECT * FROM ortak_cari WHERE strftime('%Y',tarih)=?"
    params = [str(yil)]
    if ortak: q += " AND ortak=?"; params.append(ortak)
    q += " ORDER BY tarih ASC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return jsonify(rows)

@muh.route('/api/muhasebe/ortak/ekle', methods=['POST'])
def api_ortak_ekle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        tutar = float(d['tutar'])
        iade = float(d.get('iade', 0))
        net = tutar - iade
        islem_tipi = d.get('islem_tipi', 'Ortak Gider (Kendi Cebinden)')
        conn.execute("""
            INSERT INTO ortak_cari
            (tarih,ortak,belge_no,aciklama,gider_kategori,tutar,odeme_sekli,iade,otel)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (d['tarih'], d['ortak'], d.get('belge_no', ''), d['aciklama'],
              d.get('gider_kategori', ''), tutar,
              d.get('odeme_sekli', ''), iade, d.get('otel', 'GENEL')))
        if net > 0:
            ortak_hesap = '500-LK' if d['ortak'] == 'LK' else '500-BT'
            odeme = d.get('odeme_sekli', '')
            banka_hesap = '100' if 'Nakit' in odeme else '102-2' if 'Ziraat' in odeme else '102-3' if 'Deniz' in odeme else '102-1'

            if islem_tipi == 'Ortaga Geri Odeme':
                # Şirket ortağa geri ödüyor: 500-LK/BT borcu kapanır
                mdb._yevmiye_ekle(conn, d['tarih'], 'Ortağa Geri Ödeme',
                                  ortak_hesap, banka_hesap,
                                  net, d['aciklama'], d.get('otel','GENEL'))
            else:
                # Ortak kendi cebinden ödedi: şirkete borç doğdu
                gider_hesap = '741' if 'Market' in d.get('gider_kategori','') else                               '742' if 'Tamir' in d.get('gider_kategori','') else                               '740' if 'Elektrik' in d.get('gider_kategori','') else '780'
                # Önce gider kaydı
                mdb._yevmiye_ekle(conn, d['tarih'], 'Ortak Gider (Kendi Cebinden)',
                                  gider_hesap, ortak_hesap,
                                  net, d['aciklama'], d.get('otel','GENEL'))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Mizan ───────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/mizan')
@login_required
def api_mizan():
    yil = request.args.get('yil', date.today().year, type=int)
    conn = mdb.get_conn()

    # Tüm hesapları al
    hesaplar = [dict(r) for r in conn.execute(
        "SELECT * FROM hesaplar WHERE aktif=1 ORDER BY kod").fetchall()]

    # Her hesap için yevmiyeden borç/alacak toplamları
    def hesap_toplam(kod):
        borc = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND borc_hesap=?",
            (yil, kod)).fetchone()[0] or 0
        alacak = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) FROM yevmiye WHERE yil=? AND alacak_hesap=?",
            (yil, kod)).fetchone()[0] or 0
        return borc, alacak

    satirlar = []
    gruplar = {
        'Aktif':    ('AKTİF (VARLIKLAR)', []),
        'Pasif':    ('PASİF (YÜKÜMLÜLÜKLER)', []),
        'Gelir':    ('GELİRLER', []),
        'Gider':    ('GİDERLER', []),
        'Ozkaynak': ('ÖZKAYNAKLAR', []),
    }

    toplam_borc = 0
    toplam_alacak = 0

    for tip, (baslik, rows) in gruplar.items():
        tip_hesaplar = [h for h in hesaplar if h['tip'] == tip]
        if not tip_hesaplar:
            continue
        satirlar.append({'tip': 'baslik', 'kod': '━━', 'ad': baslik, 'borc': 0, 'alacak': 0})
        for h in tip_hesaplar:
            borc, alacak = hesap_toplam(h['kod'])
            if borc == 0 and alacak == 0:
                continue
            toplam_borc += borc
            toplam_alacak += alacak
            bakiye = alacak - borc if tip in ('Gelir', 'Pasif', 'Ozkaynak') else borc - alacak
            satirlar.append({
                'tip': 'veri', 'kod': h['kod'], 'ad': h['ad'],
                'borc': borc, 'alacak': alacak, 'bakiye': bakiye
            })
        satirlar.append({'tip': 'bos'})

    # Net kar/zarar
    gelir_toplam = sum(s.get('alacak',0)-s.get('borc',0)
                       for s in satirlar if s['tip']=='veri'
                       and any(s['kod'].startswith(k) for k in ['600','601','610','611']))
    gider_toplam = sum(s.get('borc',0)-s.get('alacak',0)
                       for s in satirlar if s['tip']=='veri'
                       and any(s['kod'].startswith(k) for k in ['720','730','740','741','742','743','744','745','770','780','500']))
    net = gelir_toplam - gider_toplam

    satirlar.append({'tip': 'net', 'kod': 'NET', 'ad': 'NET KÂR / ZARAR',
                     'borc': abs(net) if net < 0 else 0,
                     'alacak': net if net >= 0 else 0,
                     'bakiye': net})

    conn.close()
    return jsonify({'satirlar': satirlar, 'net': net,
                    'toplam_borc': toplam_borc, 'toplam_alacak': toplam_alacak})


# ── API — Gelir Aktarım (Otel DB → Muhasebe DB) ───────────────────────────────

@muh.route('/api/muhasebe/gelir-aktar', methods=['POST'])
def api_gelir_aktar():
    """Otel SQLite veritabanından muhasebe gelir_ozet tablosuna aktarır."""
    try:
        import database as otel_db
        yil = request.get_json().get('yil', date.today().year)
        otel_rez = otel_db.get_rezervasyonlar()

        from collections import defaultdict
        def empty():
            return dict(konaklama=0, restoran=0, nakit=0, kk=0, havale=0, kapora=0, acik=0)
        ozet = defaultdict(empty)

        for r in otel_rez:
            giris = r.get('giris')
            if not giris: continue
            if giris[:4] != str(yil): continue
            ay = int(giris[5:7])
            otel = r.get('otel', 'LEO')
            key = (ay, otel)
            ozet[key]['konaklama'] += float(r.get('toplam_fiyat') or 0)
            ozet[key]['kapora']    += float(r.get('kapora') or 0)
            odeme = str(r.get('rez_odeme_sekli') or '').lower()
            tah = float(r.get('rez_tahsilat') or 0)
            if 'nakit' in odeme:   ozet[key]['nakit'] += tah
            elif 'kk' in odeme or 'kart' in odeme: ozet[key]['kk'] += tah
            elif 'havale' in odeme or 'eft' in odeme: ozet[key]['havale'] += tah
            adis_odeme = str(r.get('adis_odeme_sekli') or '').lower()
            adis_tah = float(r.get('adis_tahsilat') or 0)
            if 'nakit' in adis_odeme:   ozet[key]['nakit'] += adis_tah
            elif 'kk' in adis_odeme or 'kart' in adis_odeme: ozet[key]['kk'] += adis_tah
            elif 'havale' in adis_odeme: ozet[key]['havale'] += adis_tah

        # Adisyonlar restoran geliri
        otel_adis = otel_db.get_adisyonlar()
        for a in otel_adis:
            tarih = a.get('tarih')
            if not tarih or tarih[:4] != str(yil): continue
            ay = int(tarih[5:7])
            otel = a.get('otel') or 'LEO'
            ozet[(ay, otel)]['restoran'] += float(a.get('tutar') or 0)
            ozet[(ay, otel)]['acik'] += float(a.get('tutar') or 0) - float(a.get('tutar') or 0)

        # Açık bakiye
        for r in otel_rez:
            giris = r.get('giris')
            if not giris or giris[:4] != str(yil): continue
            ay = int(giris[5:7])
            otel = r.get('otel', 'LEO')
            ozet[(ay, otel)]['acik'] += float(r.get('rez_bakiye') or 0) + float(r.get('adis_bakiye') or 0)

        # Rezervasyonları ay/otel bazında grupla (gerçek tarihler için)
        from collections import defaultdict
        rez_gruplar = defaultdict(list)
        for r in otel_rez:
            giris = r.get('giris')
            if not giris or giris[:4] != str(yil): continue
            ay = int(giris[5:7])
            otel = r.get('otel', 'LEO')
            rez_gruplar[(ay, otel)].append(dict(r))

        mdb.temizle_gelir_ozet(yil)
        count = 0
        for (ay, otel), d in sorted(ozet.items()):
            rez_listesi = rez_gruplar.get((ay, otel), [])
            mdb.kaydet_gelir_ozet(yil, ay, otel, d['konaklama'], d['restoran'],
                                  d['nakit'], d['kk'], d['havale'], d['kapora'], d['acik'],
                                  rezervasyonlar=rez_listesi)
            count += 1

        return jsonify({'ok': True, 'kayit': count, 'yil': yil})
    except Exception as e:
        import traceback
        return jsonify({'ok': False, 'error': str(e), 'trace': traceback.format_exc()}), 400

# ── Sil Route'ları ────────────────────────────────────────────────────────────

@muh.route('/api/muhasebe/stok/sil', methods=['POST'])
def api_stok_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("DELETE FROM yevmiye WHERE kaynak_tablo='stok' AND kaynak_id=?", (d['id'],))
        conn.execute('DELETE FROM stok WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/vergi/sil', methods=['POST'])
def api_vergi_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("DELETE FROM yevmiye WHERE kaynak_tablo='vergi' AND kaynak_id=?", (d['id'],))
        conn.execute('DELETE FROM vergi WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/personel/maas/sil', methods=['POST'])
def api_maas_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("DELETE FROM yevmiye WHERE kaynak_tablo='personel_maas' AND kaynak_id=?", (d['id'],))
        conn.execute('DELETE FROM personel_maas WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/ortak-cari/sil', methods=['POST'])
def api_ortak_cari_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute('DELETE FROM ortak_cari WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/kasa/sil', methods=['POST'])
def api_kasa_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute('DELETE FROM yevmiye WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/acente/sil', methods=['POST'])
def api_acente_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("DELETE FROM yevmiye WHERE kaynak_tablo='acente_cari' AND kaynak_id=?", (d['id'],))
        conn.execute('DELETE FROM acente_cari WHERE id=?', (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

# ── Güncelle Route'ları ───────────────────────────────────────────────────────

@muh.route('/api/muhasebe/stok/guncelle', methods=['POST'])
def api_stok_guncelle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("""UPDATE stok SET tarih=?,belge_no=?,aciklama=?,kategori=?,tutar=?,
                     odeme_hesap=?,fatura_var=?,otel=?,not_=? WHERE id=?""",
            (d['tarih'], d.get('belge_no',''), d['aciklama'], d.get('kategori',''),
             float(d['tutar']), d.get('odeme_hesap',''), int(d.get('fatura_var',False)),
             d.get('otel','GENEL'), d.get('not_',''), d['id']))
        # Yevmiye güncelle
        conn.execute("""UPDATE yevmiye SET tarih=?,tutar=?,aciklama=?,alacak_hesap=?
                     WHERE kaynak_tablo='stok' AND kaynak_id=?""",
            (d['tarih'], float(d['tutar']), f"{d.get('kategori','')}: {d['aciklama']}",
             d.get('odeme_hesap','100'), d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/vergi/guncelle', methods=['POST'])
def api_vergi_guncelle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("""UPDATE vergi SET tarih=?,vergi_turu=?,matrah=?,tutar=?,
                     odeme_banka=?,durum=?,aciklama=? WHERE id=?""",
            (d.get('tarih',''), d['vergi_turu'], float(d.get('matrah',0)),
             float(d['tutar']), d.get('odeme_banka',''), d.get('durum','Bekliyor'),
             d.get('aciklama',''), d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/personel/maas/guncelle', methods=['POST'])
def api_maas_guncelle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        yol = float(d.get('yol_parasi', 0))
        mesai = float(d.get('fazla_mesai', 0))
        izin = float(d.get('izin_parasi', 0))
        toplam = float(d['net_odeme']) + yol + mesai + izin
        conn.execute("""UPDATE personel_maas SET tarih=?,net_odeme=?,yol_parasi=?,fazla_mesai=?,izin_parasi=?,gelmedi_gun=?,odeme_banka=?,aciklama=?,otel=?
                     WHERE id=?""",
            (d['tarih'], float(d['net_odeme']), yol, mesai, izin,
             int(d.get('gelmedi_gun',0)), d.get('odeme_banka',''),
             d.get('aciklama',''), d.get('otel','GENEL'), d['id']))
        conn.execute("""UPDATE yevmiye SET tarih=?,tutar=?,alacak_hesap=?
                     WHERE kaynak_tablo='personel_maas' AND kaynak_id=?""",
            (d['tarih'], toplam, d.get('odeme_banka','102-1'), d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/ortak-cari/guncelle', methods=['POST'])
def api_ortak_cari_guncelle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("""UPDATE ortak_cari SET tarih=?,aciklama=?,tutar=?,iade=?,
                     odeme_sekli=?,gider_kategori=?,otel=? WHERE id=?""",
            (d['tarih'], d['aciklama'], float(d['tutar']), float(d.get('iade',0)),
             d.get('odeme_sekli',''), d.get('gider_kategori',''), d.get('otel','GENEL'), d['id']))
        conn.execute("""UPDATE yevmiye SET tarih=?,tutar=?,aciklama=?
                     WHERE kaynak_tablo='ortak_cari' AND kaynak_id=?""",
            (d['tarih'], float(d['tutar']), d['aciklama'], d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/demirbas/guncelle', methods=['POST'])
def api_demirbas_guncelle():
    try:
        d = request.get_json()
        toplam = float(d.get('miktar',1)) * float(d['birim_fiyat'])
        conn = mdb.get_conn()
        conn.execute("""UPDATE [demirbaş] SET tarih=?,aciklama=?,miktar=?,birim_fiyat=?,
                     toplam=?,odeme_hesap=?,fatura_no=?,otel=?,not_=? WHERE id=?""",
            (d['tarih'], d['aciklama'], float(d.get('miktar',1)), float(d['birim_fiyat']),
             toplam, d.get('odeme_hesap',''), d.get('fatura_no',''),
             d.get('otel','GENEL'), d.get('not_',''), d['id']))
        conn.execute("""UPDATE yevmiye SET tarih=?,tutar=?,aciklama=?,alacak_hesap=?
                     WHERE kaynak_tablo='demirbaş' AND kaynak_id=?""",
            (d['tarih'], toplam, d['aciklama'], d.get('odeme_hesap','100'), d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/acente/guncelle', methods=['POST'])
def api_acente_guncelle():
    try:
        d = request.get_json()
        komisyon = float(d.get('komisyon_tl', 0))
        gelen = float(d.get('gelen_odeme', 0))
        conn = mdb.get_conn()
        conn.execute("""UPDATE acente_cari SET tarih=?,acente_kod=?,foy_no=?,rez_no=?,
                     misafir=?,rez_tutari=?,komisyon_oran=?,komisyon_tl=?,gelen_odeme=?,otel=?
                     WHERE id=?""",
            (d['tarih'], d['acente_kod'], d.get('foy_no'), d.get('rez_no',''),
             d.get('misafir',''), float(d['rez_tutari']),
             float(d.get('komisyon_oran',15)), komisyon, gelen,
             d.get('otel','LEO'), d['id']))
        # Yevmiye güncelle
        conn.execute("""UPDATE yevmiye SET tarih=?,tutar=?
                     WHERE kaynak_tablo='acente_cari' AND kaynak_id=?""",
            (d['tarih'], komisyon or gelen, d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Personel Avans ──────────────────────────────────────────────────────

@muh.route('/api/muhasebe/avans', methods=['GET'])
def api_avans():
    personel_id = request.args.get('personel_id', type=int)
    yil = request.args.get('yil', type=int)
    ay = request.args.get('ay', type=int)
    return jsonify(mdb.get_avans(personel_id=personel_id, yil=yil, ay=ay))

@muh.route('/api/muhasebe/avans/ekle', methods=['POST'])
def api_avans_ekle():
    try:
        d = request.get_json()
        mdb.ekle_avans(d['tarih'], int(d['personel_id']),
                       float(d['tutar']), d.get('odeme_sekli', '100'),
                       d.get('aciklama', ''), d.get('otel', 'GENEL'))
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/avans/sil', methods=['POST'])
def api_avans_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("DELETE FROM yevmiye WHERE kaynak_tablo='personel_avans' AND kaynak_id=?", (d['id'],))
        conn.execute("DELETE FROM personel_avans WHERE id=?", (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ── API — Personel Güncelle / Sil ────────────────────────────────────────────

@muh.route('/api/muhasebe/personel/guncelle', methods=['POST'])
def api_personel_guncelle():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("""UPDATE personel SET ad_soyad=?,ise_giris=?,gorev=?,net_maas=?,
                     banka_iban=?,telefon=?,tc_kimlik=? WHERE id=?""",
            (d['ad_soyad'], d.get('ise_giris'), d.get('gorev'),
             float(d.get('net_maas', 0)), d.get('banka_iban', ''),
             d.get('telefon', ''), d.get('tc_kimlik', ''), d['id']))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400

@muh.route('/api/muhasebe/personel/sil', methods=['POST'])
def api_personel_sil():
    try:
        d = request.get_json()
        conn = mdb.get_conn()
        conn.execute("UPDATE personel SET aktif=0 WHERE id=?", (d['id'],))
        conn.commit(); conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
