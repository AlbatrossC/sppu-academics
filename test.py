import fitz
import cv2
import numpy as np


INPUT_PDF = "bioinformetics_2.pdf"
OUTPUT_PDF = "enhanced_2.pdf"

DPI = 600


def enhance_text(img):
    # Convert RGB -> grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Upscale using high-quality Lanczos interpolation
    gray = cv2.resize(
        gray,
        None,
        fx=1.5,
        fy=1.5,
        interpolation=cv2.INTER_LANCZOS4
    )

    # Very gentle sharpening
    blur = cv2.GaussianBlur(gray, (0, 0), 1.2)

    sharp = cv2.addWeighted(
        gray,
        1.35,
        blur,
        -0.35,
        0
    )

    # Prevent extreme values
    sharp = np.clip(sharp, 0, 255).astype(np.uint8)

    return sharp


def process_pdf():

    doc = fitz.open(INPUT_PDF)
    output = fitz.open()

    zoom = DPI / 72
    matrix = fitz.Matrix(zoom, zoom)

    for i, page in enumerate(doc):

        print(f"Processing page {i + 1}/{len(doc)}")

        # Render PDF at 600 DPI
        pix = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        # Convert to NumPy
        img = np.frombuffer(
            pix.samples,
            dtype=np.uint8
        ).reshape(
            pix.height,
            pix.width,
            3
        )

        # Enhance
        enhanced = enhance_text(img)

        # Original page dimensions
        rect = page.rect

        new_page = output.new_page(
            width=rect.width,
            height=rect.height
        )

        # PNG = LOSSLESS
        success, encoded = cv2.imencode(
            ".png",
            enhanced
        )

        if not success:
            raise RuntimeError("PNG encoding failed")

        new_page.insert_image(
            rect,
            stream=encoded.tobytes()
        )

    output.save(
        OUTPUT_PDF,
        garbage=4,
        deflate=True
    )

    output.close()
    doc.close()

    print("Done!")
    print(f"Saved: {OUTPUT_PDF}")


if __name__ == "__main__":
    process_pdf()