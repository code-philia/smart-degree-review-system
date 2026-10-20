const app = require('./app');
const { initializeDatabase } = require('./database/init_db');
const { createArchiveScanService } = require('./normative/archiveScanService');
const paperLintJobService = require('./normative/paperLintJobService');

const defaultPort = 3000;
const port = Number(process.env.PORT || defaultPort);
const listenHost = process.env.ARC_LISTEN_HOST || undefined;
const listenAddress = listenHost || '0.0.0.0';

initializeDatabase()
  .then(async () => {
    await createArchiveScanService().resumeJobs();
    await paperLintJobService.resumeJobs();
    const onListen = () => {
      console.log(`Backend listening at http://${listenAddress}:${port}`);
    };
    if (listenHost) app.listen(port, listenHost, onListen);
    else app.listen(port, onListen);
  })
  .catch((error) => {
    console.error('Database initialization failed:', error);
    process.exitCode = 1;
  });
