# Roboto Regular advance widths, per 1000 em units.
# Validated against draw.io's own text measurements in ga1.6-hand-detection.svg:
#   /palm_detector_input_tensor 12px -> drawio 153, this table 156.7
#   /landmark_detector_output_tensor 12px -> drawio 184, this table 188.4
#   "Image raw data provider" 15px -> drawio 163, this table 162.7
# i.e. within ~2%, erring slightly wide (which only ever adds spacing).
W = {
    ' ': 248, '!': 271, '"': 340, '#': 636, '$': 568, '%': 733, '&': 603, "'": 180,
    '(': 344, ')': 344, '*': 421, '+': 568, ',': 271, '-': 340, '.': 271, '/': 361,
    '0': 568, '1': 568, '2': 568, '3': 568, '4': 568, '5': 568, '6': 568, '7': 568,
    '8': 568, '9': 568,
    ':': 271, ';': 271, '<': 533, '=': 568, '>': 533, '?': 506, '@': 869,
    'A': 656, 'B': 632, 'C': 651, 'D': 653, 'E': 573, 'F': 563, 'G': 683, 'H': 692,
    'I': 274, 'J': 543, 'K': 641, 'L': 546, 'M': 855, 'N': 700, 'O': 705, 'P': 620,
    'Q': 705, 'R': 626, 'S': 621, 'T': 588, 'U': 664, 'V': 645, 'W': 924, 'X': 620,
    'Y': 604, 'Z': 583,
    '[': 344, '\\': 361, ']': 344, '^': 479, '_': 519, '`': 340,
    'a': 543, 'b': 566, 'c': 526, 'd': 566, 'e': 533, 'f': 350, 'g': 566, 'h': 553,
    'i': 244, 'j': 244, 'k': 522, 'l': 244, 'm': 858, 'n': 553, 'o': 570, 'p': 566,
    'q': 566, 'r': 349, 's': 519, 't': 353, 'u': 553, 'v': 495, 'w': 762, 'x': 495,
    'y': 495, 'z': 470,
    '{': 344, '|': 256, '}': 344, '~': 568,
}
DEFAULT = 568


def text_width(s, size, bold=False):
    total = sum(W.get(ch, DEFAULT) for ch in s)
    w = total * size / 1000.0
    if bold:
        w *= 1.045
    return w
