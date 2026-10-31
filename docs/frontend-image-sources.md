# Frontend image sources

## Campus gate background

- Asset: `frontend/public/sjtu-portal-gate.png`
- Source portal: https://i.sjtu.edu.cn/
- Portal stylesheet: https://i.sjtu.edu.cn/css/assets/css/shjd-style.css
- Original asset: https://i.sjtu.edu.cn/css/assets/images/bdbg.png
- Dimensions: 1920 × 1080.
- The portal applies this image to `.shjd-bg`. The user explicitly requested the same image used by an SJTU portal. Preserve the original image and its source attribution.
- Served locally by this application; browsers do not contact the source portal to load the image.

The original portal line drawing is retained as an existing asset; the selected sign-in photograph is documented below.

## Siyuan monument sign-in photograph (2026-10-31)

- Local asset: `frontend/public/sjtu-siyuan-monument.jpg`.
- Source gallery: https://en.sjtu.edu.cn/about-us/discover-sjtu/photolist/?category_id=27
- Original image: https://smse.sjtu.edu.cn/storage/global/web/en/file/2025/06/a38c20f8df2cda1f62c37a347a21553b.jpg
- Dimensions: 2048 x 1397. Original JPEG bytes are preserved; this is not a 4K reconstruction.
- Served locally as the full-viewport sign-in background. Its inscription is positioned outside the login form and headline.
- No image blur, artificial water, sweeping light, particles or continuous zoom. Fine mouse pointers can move the photo by only a few pixels; it stays still at rest and on touch devices.
- Reduced-motion preferences disable parallax by default. Visitors can explicitly enable or pause it with the page control; the preference stays in their own browser.
- The visible footer credits were removed at the user's request. Source attribution remains in this repository.
