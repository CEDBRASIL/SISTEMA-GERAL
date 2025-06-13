import express, { Request, Response, NextFunction } from 'express';
import cors from 'cors';
import { create, Whatsapp } from '@wppconnect-team/wppconnect';
import winston from 'winston';

const logger = winston.createLogger({
  level: 'info',
  format: winston.format.json(),
  transports: [new winston.transports.Console()],
});

const app = express();
app.use(express.json());
app.use(
  cors({
    origin: process.env.ALLOWED_ORIGIN,
  })
);

let qrCode: string | null = null;
let status: 'loading' | 'ready' = 'loading';
let client: Whatsapp | null = null;

create({
  session: 'default',
  catchQR: (base64Qr: string) => {
    qrCode = base64Qr;
    status = 'loading';
    logger.info({ event: 'qr' });
  },
})
  .then((cl) => {
    client = cl;
    status = 'ready';
    logger.info({ event: 'ready' });
  })
  .catch((err) => {
    logger.error({ event: 'error', message: err.message });
  });

app.get('/qr', (_req: Request, res: Response) => {
  res.json({ qr: qrCode, status });
});

app.post('/send', async (req: Request, res: Response) => {
  const { numero, mensagem } = req.body ?? {};
  const regex = /^\+\d{10,15}$/;
  if (!regex.test(numero)) {
    res.status(422).json({ error: 'Número inválido' });
    logger.warn({ event: 'invalid_number', numero });
    return;
  }
  if (!client) {
    res.status(503).json({ error: 'Sessão não iniciada' });
    return;
  }
  try {
    await client.sendText(`${numero}@c.us`, mensagem);
    res.json({ success: true });
  } catch (err: any) {
    logger.error({ event: 'send_error', message: err.message });
    res.status(500).json({ error: 'Erro ao enviar mensagem' });
  }
});

// Error logging
app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
  logger.error({ event: 'internal_error', message: err.message });
  res.status(500).json({ error: 'Erro interno' });
});

const port = Number(process.env.PORT) || 10000;
app.listen(port, () => {
  logger.info({ event: 'listening', port });
});
