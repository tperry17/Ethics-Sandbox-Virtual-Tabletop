# Remove the printed frame from the Value Cards' face pictures.
#
#   uv run --with pillow --with numpy --with scipy python -I \
#       scripts/unframe-card-faces.py <folder of framed .jpg> <output folder>
#
# The input is the Drive folder "Value Cards" files "valuecards with
# frames_NN.jpg" (NN is the number printed on the card), saved as NN.jpg.
# The output NN.jpg files go to content/decks/value-cards/images/faces/ under
# the card's name (the `face` column of cards.csv). Pillow, NumPy and SciPy
# are not project dependencies: uv fetches them for this one run.
"""Paint out the printed frame on each card image and crop to where it was.

The frame is the one connected run of frame-coloured pixels that touches the
middle of the image's left side. Everything in that run (and a three-pixel
halo of antialiasing around it) is painted white; the number, the icon and
the picture are not connected to it and are left alone. The image is then
cropped to the frame's outer bounds.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

source, target = Path(sys.argv[1]), Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)

for path in sorted(source.glob("*.jpg")):
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(int)
    height, width, _ = rgb.shape
    middle = height // 2
    # The frame's colour: the darkest pixel along the left edge's middle row.
    row = rgb[middle, : width // 6]
    seed_x = int(np.argmin(row.sum(axis=1)))
    colour = rgb[middle, seed_x]
    distance = np.abs(rgb - colour).sum(axis=2)
    near = distance < 150
    labels, _ = ndimage.label(near)
    frame = labels == labels[middle, seed_x]
    ys, xs = np.nonzero(frame)
    frame = ndimage.binary_dilation(frame, iterations=3)
    out = rgb.copy()
    out[frame] = 255
    top, bottom, left, right = ys.min(), ys.max(), xs.min(), xs.max()
    cropped = out[top : bottom + 1, left : right + 1].astype(np.uint8)
    Image.fromarray(cropped).save(target / path.name, quality=90)
    print(
        path.name,
        tuple(int(c) for c in colour),
        (left, top, right, bottom),
        frame.sum(),
    )
