// Enkoder güncelleme paketindeki CRC-8'in bilgisayarda testi (Pico SDK gerekmez).
//
// Stator'un paketi kurduğu ve rotorun doğruladığı kod yolunu aynen kullanır:
// paket RS485 ayrıştırıcısından geçirilir, rotorun CRC kontrolü uygulanır.
// Bütün 1, 2 ve 3 bitlik hatalar (sync dahil, paketin her bitinde) denenir;
// hiçbirinin YANLIŞ bir enkoder değeri olarak kabul edilmemesi gerekir.
//
//   g++ -std=c++17 -I../include enkoder_crc_testi.cpp -o /tmp/enkoder_crc_testi && /tmp/enkoder_crc_testi
//   (-DCRC_KONTROLU_KAPALI ile derlenirse yanlış kabuller görülmeli: test gerçekten sınıyor)
//
// host/tests/test_firmware_crc.py bunu pytest içinden derleyip çalıştırır.
#include <cstdio>
#include <cstring>

#include "crc.h"
#include "mgf_protocol.h"
#include "rs485_framing.h"

static int32_t kabul_edilen_enkoder;
static uint16_t kabul_edilen_seq;
static int kabul_sayisi;

// rotor.cpp:handle_incoming içindeki enkoder dalının aynısı
static void rotor_geri_cagirma(uint8_t type, const uint8_t *pkt, size_t) {
    if (type != RS485_TYPE_ENC_UPDATE) return;
#ifndef CRC_KONTROLU_KAPALI  // testin kendisini sınamak için: kapalıyken yanlış kabuller görülmeli
    if (crc8(&pkt[2], sizeof(EncUpdatePacket) - 3) != pkt[sizeof(EncUpdatePacket) - 1]) return;
#endif
    EncUpdatePacket p;
    memcpy(&p.encoder, &pkt[3], 6);
    kabul_edilen_enkoder = p.encoder;
    kabul_edilen_seq = p.seq;
    kabul_sayisi++;
}

// stator.cpp'deki paket kurulumunun aynısı
static EncUpdatePacket paket_kur(int32_t enc, uint16_t seq) {
    EncUpdatePacket pkt;
    pkt.sync = RS485_SYNC_WORD;
    pkt.type = RS485_TYPE_ENC_UPDATE;
    pkt.encoder = enc;
    pkt.seq = seq;
    pkt.crc = crc8(&pkt.type, sizeof(pkt) - 3);
    return pkt;
}

// Paketi (ardından aynı değerde sağlam bir paket) ayrıştırıcıdan geçirir.
// Dönen: bozuk paketten yanlış bir değer kabul edildi mi.
static bool yanlis_kabul(const uint8_t *bayt, int32_t enc, uint16_t seq) {
    static uint8_t halka[64];
    mgf::RS485Parser ayristirici(halka, sizeof(halka));
    kabul_sayisi = 0;
    bool yanlis = false;
    memcpy(halka, bayt, sizeof(EncUpdatePacket));
    ayristirici.parse(sizeof(EncUpdatePacket), [](uint8_t t, const uint8_t *p, size_t n) {
        rotor_geri_cagirma(t, p, n);
    });
    if (kabul_sayisi > 0 && (kabul_edilen_enkoder != enc || kabul_edilen_seq != seq)) yanlis = true;
    return yanlis;
}

int main() {
    static_assert(sizeof(EncUpdatePacket) == 10, "paket boyu");
    const int32_t degerler[] = {0, 1, -1, 123456, -7654321, 0x55AA55AA, 2147483647};
    const int nbit = sizeof(EncUpdatePacket) * 8;
    long deneme = 0, yanlis = 0;
    int seq = 0;

    for (int32_t enc : degerler) {
        EncUpdatePacket pkt = paket_kur(enc, (uint16_t)seq);
        uint8_t sag[sizeof(pkt)];
        memcpy(sag, &pkt, sizeof(pkt));

        // Sağlam paket kabul edilmeli
        kabul_sayisi = 0;
        yanlis_kabul(sag, enc, (uint16_t)seq);
        if (kabul_sayisi != 1 || kabul_edilen_enkoder != enc) {
            printf("HATA: saglam paket kabul edilmedi (enc=%d)\n", enc);
            return 1;
        }
        for (int a = 0; a < nbit; a++) {
            for (int b = a; b < nbit; b++) {
                for (int c = b; c < nbit; c++) {
                    // a == b == c: tek bit; a < b == c: iki bit; a < b < c: üç bit
                    if (a == b && b != c) continue;
                    uint8_t boz[sizeof(pkt)];
                    memcpy(boz, sag, sizeof(pkt));
                    boz[a / 8] ^= 1u << (a % 8);
                    if (b != a) boz[b / 8] ^= 1u << (b % 8);
                    if (c != b) boz[c / 8] ^= 1u << (c % 8);
                    deneme++;
                    if (yanlis_kabul(boz, enc, (uint16_t)seq)) {
                        yanlis++;
                        if (yanlis <= 5)
                            printf("YANLIS KABUL: enc=%d bitler %d %d %d -> %d\n", enc, a, b, c,
                                   kabul_edilen_enkoder);
                    }
                }
            }
        }
        seq += 7919;
    }
    printf("deneme=%ld yanlis_kabul=%ld\n", deneme, yanlis);
    return yanlis == 0 ? 0 : 1;
}
