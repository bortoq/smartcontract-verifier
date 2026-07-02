/* bitcpy.c — copy bits MSB-first with overlap-safe fallback
 *
 * bit positions within a byte: 0..7 correspond to masks 0x80,0x40,...,0x01.
 *
 * If src_org == dst_org and bit ranges overlap, we do memmove-like bit copy.
 * Otherwise we do a faster copy with masks/shifts.
 */

#include <string.h>
#include <stdint.h>
#include <stddef.h>

static inline unsigned bit_get_ptr(const uint8_t *p, size_t bitpos) {
  uint8_t byte = p[bitpos >> 3];
  unsigned shift = 7u - (unsigned)(bitpos & 7u);
  return (byte >> shift) & 1u;
}

static inline void bit_set_ptr(uint8_t *p, size_t bitpos, unsigned v) {
  uint8_t *b = &p[bitpos >> 3];
  unsigned shift = 7u - (unsigned)(bitpos & 7u);
  uint8_t mask = (uint8_t)(1u << shift);
  if (v) *b |= mask;
  else   *b &= (uint8_t)~mask;
}

static void bitcpy_overlap_fallback(size_t n_bits,
                                    const uint8_t *src, size_t src_bit,
                                    uint8_t *dst, size_t dst_bit)
{
  if (dst_bit < src_bit) {
    for (size_t i = 0; i < n_bits; i++) {
      bit_set_ptr(dst, dst_bit + i, bit_get_ptr(src, src_bit + i));
    }
  } else {
    for (size_t i = n_bits; i-- > 0;) {
      bit_set_ptr(dst, dst_bit + i, bit_get_ptr(src, src_bit + i));
    }
  }
}

void bitcpy(size_t n_bits,
            const void *src_org, size_t src_bit,
            void *dst_org, size_t dst_bit)
{
  if (n_bits == 0) return;
  if (src_org == dst_org && src_bit == dst_bit) return;

  if (n_bits < 8) {
    bitcpy_overlap_fallback(n_bits,
                            (const uint8_t*)src_org, src_bit,
                            (uint8_t*)dst_org, dst_bit);
    return;
  }

  const uint8_t *src0 = (const uint8_t*)src_org;
  uint8_t *dst0 = (uint8_t*)dst_org;

  /* overlap check (only meaningful if same base buffer) */
  if (src_org == dst_org) {
    size_t src_end = src_bit + n_bits;
    size_t dst_end = dst_bit + n_bits;
    if (src_bit < dst_end && dst_bit < src_end) {
      bitcpy_overlap_fallback(n_bits, src0, src_bit, dst0, dst_bit);
      return;
    }
  }

  /* MSB-first masks */
  static const uint8_t keep_hi[9] = { /* top k bits =1 */
    0x00, 0x80, 0xC0, 0xE0, 0xF0, 0xF8, 0xFC, 0xFE, 0xFF
  };
  static const uint8_t keep_lo[9] = { /* bottom (8-k) bits =1 */
    0xFF, 0x7F, 0x3F, 0x1F, 0x0F, 0x07, 0x03, 0x01, 0x00
  };

  size_t src_byte = src_bit >> 3;
  size_t dst_byte = dst_bit >> 3;
  unsigned src_mod = (unsigned)(src_bit & 7u);
  unsigned dst_mod = (unsigned)(dst_bit & 7u);

  const uint8_t *src = src0 + src_byte;
  uint8_t *dst = dst0 + dst_byte;

  /* Fast byte-aligned path. */
  if (((src_bit | dst_bit) & 7u) == 0u) {
    size_t nbytes = n_bits >> 3;
    size_t rem = n_bits & 7u;
    if (nbytes) {
      memmove(dst, src, nbytes);
      dst += nbytes;
      src += nbytes;
    }
    if (rem) {
      uint8_t mask = keep_hi[rem];
      *dst = (uint8_t)((*dst & (uint8_t)~mask) | (*src & mask));
    }
    return;
  }

  /* Same bit offset: align once, then bulk-copy whole bytes. */
  if (src_mod == dst_mod) {
    if (dst_mod) {
      unsigned head = 8u - dst_mod;
      if (head > n_bits) head = (unsigned)n_bits;

      uint8_t s = (uint8_t)(*src & keep_lo[dst_mod]);
      uint8_t mask_keep = (uint8_t)(keep_hi[dst_mod] | keep_lo[dst_mod + head]);
      *dst = (uint8_t)((*dst & mask_keep) | (s & (uint8_t)~mask_keep));

      n_bits -= head;
      dst++; src++;
    }

    while (n_bits >= 64) {
      uint64_t a, b, w;
      memcpy(&a, src, sizeof(a));
      memcpy(&b, src + 8, sizeof(b));
      if (src_mod == 0u) {
        w = a;
      } else {
        unsigned s = src_mod;
        w = (a << s) | (b >> (64u - s));
      }
      memcpy(dst, &w, sizeof(w));
      src += 8;
      dst += 8;
      n_bits -= 64;
    }

    size_t nbytes = n_bits >> 3;
    if (nbytes) {
      memmove(dst, src, nbytes);
      dst += nbytes;
      src += nbytes;
      n_bits -= (nbytes << 3);
    }

    if (n_bits) {
      unsigned tail = (unsigned)n_bits; /* 1..7 */
      uint8_t mask = keep_hi[tail];
      *dst = (uint8_t)((*dst & (uint8_t)~mask) | (*src & mask));
    }
    return;
  }

  if (dst_mod) {
    unsigned head = 8u - dst_mod;
    if (head > n_bits) head = (unsigned)n_bits;

    unsigned left = src_mod > dst_mod ? (src_mod - dst_mod) : (8u - (dst_mod - src_mod));
    unsigned right = 8u - left;
    uint8_t c = (uint8_t)(src[0] << left);
    c |= (uint8_t)(src[1] >> right);

    uint8_t mask_keep = (uint8_t)(keep_hi[dst_mod] | keep_lo[dst_mod + head]);
    *dst = (uint8_t)((*dst & mask_keep) | (c & (uint8_t)~mask_keep));

    n_bits -= head;
    dst++;
    if (src_mod > dst_mod) src++;
  }

  /* 64-bit sliding window for the bulk body. */
  while (n_bits >= 64) {
    uint64_t a, b;
    memcpy(&a, src, sizeof(a));
    memcpy(&b, src + 8, sizeof(b));
    unsigned left = src_mod > dst_mod ? (src_mod - dst_mod) : (8u - (dst_mod - src_mod));
    unsigned right = 8u - left;
    uint64_t w = (a << left) | (b >> right);
    memcpy(dst, &w, sizeof(w));
    src += 8;
    dst += 8;
    n_bits -= 64;
  }

  while (n_bits >= 8) {
    unsigned left = src_mod > dst_mod ? (src_mod - dst_mod) : (8u - (dst_mod - src_mod));
    unsigned right = 8u - left;
    uint8_t c = (uint8_t)(src[0] << left);
    c |= (uint8_t)(src[1] >> right);
    *dst++ = c;
    src++;
    n_bits -= 8;
  }

  if (n_bits) {
    unsigned left = src_mod > dst_mod ? (src_mod - dst_mod) : (8u - (dst_mod - src_mod));
    unsigned right = 8u - left;
    uint8_t c = (uint8_t)(src[0] << left);
    c |= (uint8_t)(src[1] >> right);
    uint8_t mask = keep_hi[n_bits];
    *dst = (uint8_t)((*dst & (uint8_t)~mask) | (c & mask));
  }
}
