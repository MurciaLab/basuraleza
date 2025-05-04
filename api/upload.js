export const config = {
    api: {
      bodyParser: false, // Disable body parsing to handle raw body manually
    },
  };
  
  export default async function handler(req, res) {
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };
  
    // Handle preflight request
    if (req.method === "OPTIONS") {
      res.set(corsHeaders).status(204).end();
      return;
    }
  
    if (req.method !== "POST") {
      res.set(corsHeaders).status(405).end("Method not allowed");
      return;
    }
  
    // Read raw body from request
    const bodyChunks = [];
    for await (const chunk of req) {
      bodyChunks.push(chunk);
    }
    const bodyBuffer = Buffer.concat(bodyChunks);
  
    try {
      const response = await fetch("https://script.google.com/macros/s/AKfycbzb6zDBq-8G5WIMygB7zbeEPIBnf0WgonJIDpuB83TA7kqCI5uyd1R7FjDU1g20TwY/exec", {
        method: "POST",
        headers: {
          "Content-Type": req.headers["content-type"],
        },
        body: bodyBuffer,
      });
  
      const responseText = await response.text();
  
      res.set(corsHeaders).status(response.status).send(responseText);
    } catch (err) {
      console.error("Proxy error:", err);
      res.set(corsHeaders).status(500).json({
        status: "error",
        message: err.message,
      });
    }
  }
  