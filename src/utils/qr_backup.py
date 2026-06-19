import io


def normalize_qr_payload(qr_data: str) -> str:
    payload = (qr_data or "").strip()
    lower_payload = payload.lower()
    for command in (".importbackup", "/importbackup"):
        if lower_payload.startswith(command):
            return payload[len(command):].strip()
    return payload


def build_qr_image(qr_data: str) -> io.BytesIO:
    payload = normalize_qr_payload(qr_data)
    if not payload:
        raise ValueError("QR backup payload is empty")

    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.name = "grouphelp-importbackup.png"
    output.seek(0)
    return output


def decode_qr_image_payload(image_bytes: bytes) -> str:
    if not image_bytes:
        raise ValueError("QR image is empty")

    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    except Exception as e:
        raise ValueError(f"Could not open image: {e}") from e

    detector = cv2.QRCodeDetector()
    rgb = np.asarray(image)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    candidates = [bgr, gray]
    height, width = gray.shape[:2]
    if min(height, width) < 900:
        scale = max(2, int(900 / max(1, min(height, width))))
        candidates.extend([
            cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC),
            cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC),
        ])

    for candidate in candidates:
        data, _, _ = detector.detectAndDecode(candidate)
        payload = normalize_qr_payload(data)
        if payload:
            return payload

        ok, decoded, _, _ = detector.detectAndDecodeMulti(candidate)
        if ok:
            for item in decoded:
                payload = normalize_qr_payload(item)
                if payload:
                    return payload

    raise ValueError("No QR code could be decoded from the image")
