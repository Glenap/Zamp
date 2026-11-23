import { mkdir, readFile, readdir, writeFile, cp } from 'node:fs/promises';
import { resolve, relative, extname } from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const root = fileURLToPath(new URL('..', import.meta.url));
const repo = resolve(root, '../..');
process.chdir(root);
execFileSync(process.env.PYTHON || 'python', ['scripts/prepare_fixtures.py'], { stdio: 'inherit' });
const client = resolve(repo, 'frontend/dist');
const assets = {};
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.woff2': 'font/woff2' };
async function collect(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, item.name);
    if (item.isDirectory()) await collect(path);
    else assets['/' + relative(client, path).replaceAll('\\', '/')] = { base64: (await readFile(path)).toString('base64'), type: types[extname(path)] || 'application/octet-stream' };
  }
}
await collect(client);
await mkdir('worker/generated', { recursive: true });
await writeFile('worker/generated/client.json', JSON.stringify(assets));
await mkdir('dist/server', { recursive: true });
await build({ entryPoints: ['worker/index.js'], outfile: 'dist/server/index.js', bundle: true, format: 'esm', platform: 'browser', target: 'es2022', minify: true, external: ['cloudflare:workers'] });
await mkdir('dist/.openai', { recursive: true });
await cp('.openai/hosting.json', 'dist/.openai/hosting.json');
await cp('drizzle', 'dist/.openai/drizzle', { recursive: true });
await writeFile('dist/server/wrangler.json', JSON.stringify({ name: 'vendorgate-local', main: 'index.js', compatibility_date: '2026-05-15', d1_databases: [{ binding: 'DB', database_name: 'vendorgate-local', database_id: '00000000-0000-0000-0000-000000000001', migrations_dir: '../.openai/drizzle' }], r2_buckets: [{ binding: 'BUCKET', bucket_name: 'vendorgate-local' }] }, null, 2));
console.log('Built VendorGate Worker, bundled React assets, fixture PDFs and schema migrations.');
await cp('dist', resolve(repo, 'dist'), { recursive: true });
