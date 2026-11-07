# Completion email configuration

New website detection jobs and incremental reruns save a completion notification in SQLite when their report is committed. Existing jobs remain excluded during migration. The email worker is separate from detection and polls every 15 seconds. Missing mail configuration preserves the pending queue without attempting delivery. Five unsuccessful attempts leave a failed row for operator inspection; after fixing the cause, operators can requeue the affected failed rows without rerunning detection. SMTP acceptance does not guarantee inbox delivery, and a crash after acceptance can cause redelivery with the same Message-ID.

The four local trial identities (student01, supervisor01, college_admin01, school_admin01) and all administrator roles use `123090058@link.cuhk.edu.cn`. Other jAccount users use the authenticated profile email, or their institutional `account@sjtu.edu.cn` mailbox if the essential profile omits email. Campus notification destinations are server-controlled. Existing active sessions receive the same fallback without having to sign in again.

Add these values to the service's protected server configuration once the mailbox administrator has authorized sending:

```dotenv
REPORT_EMAIL_ENABLED=1
APP_PUBLIC_URL=http://121.36.247.138:3000
SMTP_HOST=mail.sjtu.edu.cn
SMTP_PORT=465
SMTP_USER=gs.xwb1@sjtu.edu.cn
SMTP_FROM_ADDRESS=gs.xwb1@sjtu.edu.cn
SMTP_FROM_NAME=研究生学位信息系统
SMTP_PASSWORD_FILE=/path/to/service-readable/protected-smtp-password
```

Use a file readable only by the service account and administrators, with restrictive parent directory permissions. A protected `SMTP_PASSWORD` environment variable is also supported. Do not put credentials in this repository. The jAccount client secret is not a mail credential. The mailbox administrator must confirm the SMTP account/server details; the SJTU public mailbox documentation lists mail.sjtu.edu.cn and TLS port 465: https://net.sjtu.edu.cn/xxfw/dzyj.htm .

Restart the service after configuration. Confirm SMTP authorization and send one authorized test report to the designated local-account recipient before announcing delivery as available. Until then sending remains disabled and queued notifications are preserved. The task card uses the requested completion message without displaying SMTP configuration status.

The dynamic ETA uses recent comparable completed tasks, elapsed execution time, observed rule progress and the queue ahead. It shows one approximate minute value and keeps recalculating after the historical duration window is exceeded, including for slow tasks ahead in the queue. When neither history nor observed progress is sufficient, estimation remains in progress. New tasks record their actual start time; legacy measurements use the available submission-to-completion duration. The website completion message is independent of SMTP availability; the actual email worker still requires the sender authorization described above.
