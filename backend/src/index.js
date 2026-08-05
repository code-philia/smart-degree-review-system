const app = require('./app');
const { initializeDatabase } = require('./database/init_db');
const seedDatabase = require('./database/seed_db');

const defaultPort = 3000;
const port = Number(process.env.PORT || defaultPort);

initializeDatabase()
  .then(() => seedDatabase())
  .then(() => {
    app.listen(port, () => {
      console.log(`Backend listening at http://127.0.0.1:${port}`);
    });
  })
  .catch((error) => {
    console.error('Database initialization failed:', error);
    process.exitCode = 1;
  });
