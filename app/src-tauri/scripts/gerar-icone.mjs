import { chromium } from 'playwright';

const navegador = await chromium.launch({ headless: true });
try {
  const pagina = await navegador.newPage({ viewport: { width: 1024, height: 1024 }, deviceScaleFactor: 1 });
  await pagina.goto('http://localhost:5173/lab/orb?solo=720&state=idle&color=%23E2ECFF&t=4&rot=0.7&glow=1', { waitUntil: 'networkidle' });
  await pagina.addStyleTag({
    content: `
      html, body, #root { width: 1024px !important; height: 1024px !important; margin: 0 !important; background: transparent !important; overflow: hidden !important; }
      .orb-lab-solo { width: 1024px !important; height: 1024px !important; display: grid !important; place-items: center !important; background: #0B0F1A !important; border-radius: 224px !important; }
    `,
  });
  await pagina.screenshot({ path: 'src-tauri/icons/sora-icon-1024.png', omitBackground: true });
} finally {
  await navegador.close();
}
