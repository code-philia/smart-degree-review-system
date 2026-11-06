# Report completion email

The user authorized implementation, main integration and external deployment. Every newly submitted detection job, including incremental reruns, should produce one completion notification after its report is saved. The four local trial accounts student01, supervisor01, college_admin01 and school_admin01, and any additional administrator accounts, use 123090058@link.cuhk.edu.cn. Other accounts use their own notification email. Existing completed jobs must not generate a historical email flood.

Use the existing SQLite job queue and an independent durable email outbox. Complete the detection job and insert its unique outbox row in one database transaction. A leased worker sends outside the detection queue, retries temporary errors with bounded backoff, and resumes after a restart. A cancelled or failed detection has no completion email. Deleting a report prevents an unsent email. SMTP acceptance is the delivery boundary; an unavoidable crash after acceptance may cause redelivery with the same Message-ID.

Persist a user's notification email. jAccount profile.email is available only under profile/privacy scopes; preserve the existing essential permission. When no email is returned, an authenticated campus account's institutional mailbox is account@sjtu.edu.cn, as documented by SJTU. Legacy local users can supply their own email. Administrators cannot override the mandated destination through client input.

The email contains the filename, completion time, the same displayed counts and incomplete-rule explanation as the report, and a report link under a configured public site origin. Include HTML and plain text, without PDF attachments. Report authorization remains unchanged; preserve the requested report destination through login using a validated local path.

Use Nodemailer SMTP with TLS and certificate verification. Credentials exist only in server environment configuration. Do not use the jAccount client secret as a mail password. Configuration absence must be visible: retain pending notifications without consuming retry attempts and do not tell users an email was sent. The external host currently has no SMTP credentials; implementation and deployment can proceed, but actual delivery needs the mailbox administrator's authorization.

Alternatives considered: sending inside detection would delay jobs and couple mail failures to results; an external queue service adds infrastructure not required by this single-server project. The existing SQLite outbox is the implementation choice. Do not modify detection rules or report cards.

Acceptance: administrator routing; campus and local-user address handling; one outbox row on repeated completion; cancelled/failed jobs excluded; recoverable leases and bounded retries; report counts and unavailable reasons preserved; HTML/header injection prevented; no cross-user access or open redirects; truthful upload/progress messaging; existing authentication and job tests continue passing.

User follow-up: prioritize a prominent, harmonious front-end ETA notice. Estimate a single remaining-time number from comparable recent jobs and queued work; insufficient history says estimating, and elapsed jobs beyond the estimate say overdue. Store a new started_at timestamp. When SMTP is not configured, do not promise email delivery; explain report availability in history.
