declare namespace Cloudflare {
  interface Env {
    MIMO_API_KEY?: string;
    SESSION_SECRET?: string;
    CLOUD_DAILY_LIMIT?: string;
    VISITOR_DAILY_LIMIT?: string;
    DB?: D1Database;
    BUCKET?: R2Bucket;
  }
}
