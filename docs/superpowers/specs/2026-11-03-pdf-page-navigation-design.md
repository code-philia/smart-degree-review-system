# PDF page navigation

The user requests direct page-number navigation above the PDF preview in both live and saved reports, with a polished frontend, followed by push and campus deployment.

Use the shared PdfPane/PdfViewer rather than separate report implementations. Add a compact page input, total physical PDF page count, submit action and previous/next controls. Group navigation separately from highlight/zoom tools, allowing toolbar wrapping on narrow screens. Physical PDF page numbers are the chosen convention; printed labels may differ.

Enter or the jump button navigates only to an integer from 1 through the loaded document's page count. Loading/errors disable navigation. Invalid input explains the range without moving the reader. Scroll and finding navigation update the current-page display; live-result refresh must preserve manual reading position. Replacing the PDF resets navigation. The complete-PDF link follows the displayed page after readiness.

No backend, rule, document-model or dependency changes are needed. Publish frontend assets atomically without restarting active detection work.

## Toolbar visual revision

The user rejected the initial capsule-style navigation and requested reference research and a redesign. Use the PDF.js and Syncfusion reading-toolbar patterns as references: a quiet document strip, a flat action strip, one bounded current/total page field between equal-size arrows, and clearly separated highlight/zoom/link groups. Keep every action 32px high and preserve its accessible name. Highlight mode uses a segmented selected state rather than separate outlined buttons. Do not wrap navigation in another capsule. At preview-pane widths below 32rem, center each action group on its own line; otherwise align navigation left and tools right. Truncate long filenames with the full name retained as the accessible text and hover title.

References: https://mozilla.github.io/pdf.js/web/viewer.html and https://help.syncfusion.com/document-processing/pdf/pdf-viewer/asp-net-core/navigation
