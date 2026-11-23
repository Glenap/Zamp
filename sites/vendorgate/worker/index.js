import client from './generated/client.json';
import { api, ApiError, json, fromBase64 } from './api.js';

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    try {
      if (path.startsWith('/api/') || path === '/health') return await api(request,env);
      if (!['GET','HEAD'].includes(request.method)) return json({detail:'Method not allowed'},405);
      const asset = client[path] || (!path.startsWith('/assets/') ? client['/index.html'] : null);
      if (!asset) return new Response('Not found',{status:404});
      return new Response(request.method==='HEAD'?null:fromBase64(asset.base64),{headers:{'content-type':asset.type,'cache-control':path.startsWith('/assets/')?'public, max-age=31536000, immutable':'no-cache','x-content-type-options':'nosniff','referrer-policy':'same-origin'}});
    } catch (error) {
      if (error instanceof ApiError) return json({detail:error.message},error.status);
      if (error instanceof SyntaxError || error instanceof TypeError) return json({detail:'Invalid request. Check the submitted JSON or files.'},422);
      console.error('VendorGate API failure',error?.name || 'Error');
      return json({detail:'The request could not be completed. Please retry.'},500);
    }
  },
};
