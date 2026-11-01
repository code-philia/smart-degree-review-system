# Browser PDF delivery

Authenticated PDF routes retain their ownership checks, private caching and byte-range support. Nonlinearized files receive a separate lossless, linearized browser copy so browsers can display initial pages before downloading the entire document. Originals remain available to the detection engine unchanged.

Install `qpdf` on the application server (`apt-get install --no-install-recommends qpdf` on Ubuntu). `ARC_QPDF_BINARY` can point to another installed executable. Without the tool, or if conversion fails, the route serves the original file. Processing is limited to two workers, deduplicated per source and stopped after 15 seconds. Cached copies have mode 0600 and are deleted with their report.

Browser copies use the suffix `.browser-cache` so archive scans cannot mistake them for additional source PDFs; never replace originals with them. Existing linearized PDFs are served directly. A source modified after its cached copy causes a rebuild. Neither this feature nor the progress indicator calls an external model or OCR service.

The progress ring reports the completed-rule ratio received from the background job API, rather than elapsed time. Rule completion does not imply equal remaining runtime: semantic rules can take longer. The report opens only after the backend marks the job completed and saves its report.
