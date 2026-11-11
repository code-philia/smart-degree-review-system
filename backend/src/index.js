const app = require('./app');
const { initializeDatabase } = require('./database/init_db');
const { createArchiveScanService } = require('./normative/archiveScanService');
const paperLintJobService = require('./normative/paperLintJobService');
const { campusOnlyAuth, adminPort } = require('./auth/loginPolicy');
const { createReportEmailService } = require('./notifications/reportEmailService');

const defaultPort = 3000;
const port = Number(process.env.PORT || defaultPort);
const privatePort = campusOnlyAuth() ? adminPort() : null;

initializeDatabase()
  .then(async () => {
    await require('./normative/feedbackArchive').refreshFeedbackArchiveSafely();
    await createArchiveScanService().resumeJobs();
    await paperLintJobService.resumeJobs();
    createReportEmailService().start();
    if (privatePort !== null) {
      app.listen(privatePort, '127.0.0.1', () => {
        console.log(`Private administrator API listening at http://127.0.0.1:${privatePort}`);
      });
    }
    app.listen(port, () => {
      console.log(`Backend listening at http://127.0.0.1:${port}`);
    });
  })
  .catch((error) => {
    console.error('Database initialization failed:', error);
    process.exitCode = 1;
  });
