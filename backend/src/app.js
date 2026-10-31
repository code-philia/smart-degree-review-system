const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');
const app = express();

// route modules imports
const authRoutes = require('./auth/authRoutes');
const normativeRoutes = require('./normative/normativeRoutes');
const exampleRuleRoutes = require('./example-rule-check/exampleRuleRoutes');
const internalReadinessRoutes = require('./diagnostics/internalReadinessRoutes');

// middleware imports
const corsOrigins = String(process.env.ARC_CORS_ORIGIN || '')
  .split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);
if (corsOrigins.length) {
  app.use(cors({
    credentials: true,
    origin(origin, callback) {
      if (!origin || corsOrigins.includes(origin)) return callback(null, true);
      return callback(null, false);
    },
  }));
}

// register routes
app.get('/api/health', (req, res) => {
  res.json({ code: 200, message: 'Backend Ready' });
});
app.use('/api/internal', internalReadinessRoutes);
app.use('/api/auth', bodyParser.json({ limit: '16kb' }), authRoutes);
app.use('/api/normative', normativeRoutes);
app.use('/api/example-rule-check', exampleRuleRoutes);

const { registerFrontendStatic } = require('./frontendStatic');
const frontendDistPath = path.resolve(__dirname, '../../frontend/dist');

app.use((error, req, res, next) => {
  if (error?.type === 'entity.too.large') {
    res.status(413).json({ code: 413, message: '请求内容过大，请按页面提示缩小文件或文本后重试' });
    return;
  }
  next(error);
});

if (fs.existsSync(frontendDistPath)) {
  registerFrontendStatic(app, frontendDistPath);
} else {
  app.get('/', (req, res) => {
    res
      .status(503)
      .type('html')
      .send(`<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Frontend Build Missing</title>
    <style>
      body {
        margin: 0;
        font-family: ui-sans-serif, system-ui, sans-serif;
        background: #f6f7f9;
        color: #1f2937;
      }
      main {
        max-width: 720px;
        margin: 12vh auto 0;
        padding: 24px;
      }
      section {
        background: #fff;
        border: 1px solid #d1d5db;
        border-radius: 12px;
        padding: 24px;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
      }
      h1 {
        margin-top: 0;
      }
      code {
        background: #f3f4f6;
        padding: 2px 6px;
        border-radius: 6px;
      }
    </style>
  </head>
  <body>
    <main>
      <section>
        <h1>Frontend build missing</h1>
        <p>The backend is running, but <code>frontend/dist</code> is not available yet.</p>
        <p>Build the frontend first, then start the backend so it can host the compiled site on the same port.</p>
      </section>
    </main>
  </body>
</html>`);
  });
}

module.exports = app;
