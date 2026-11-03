# PDF page navigation

The user requests direct page-number navigation above the PDF preview in both live and saved reports, with a polished frontend, followed by push and campus deployment.

Use the shared PdfPane/PdfViewer rather than separate report implementations. Add a compact page input, total physical PDF page count, submit action and previous/next controls. Group navigation separately from highlight/zoom tools, allowing toolbar wrapping on narrow screens. Physical PDF page numbers are the chosen convention; printed labels may differ.

Enter or the jump button navigates only to an integer from 1 through the loaded document's page count. Loading/errors disable navigation. Invalid input explains the range without moving the reader. Scroll and finding navigation update the current-page display; live-result refresh must preserve manual reading position. Replacing the PDF resets navigation. The complete-PDF link follows the displayed page after readiness.

No backend, rule, document-model or dependency changes are needed. Publish frontend assets atomically without restarting active detection work.
