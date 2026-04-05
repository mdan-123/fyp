import { NextResponse } from 'next/server';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { text, user_id, timezone = "UTC" } = body;

    if (!text || !user_id) {
      return NextResponse.json({ error: "Missing text or user_id" }, { status: 400 });
    }

    // Forward the request to your Python FastAPI backend
    const pythonResponse = await fetch('http://127.0.0.1:8000/api/ai/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, user_id, timezone }),
    });

    if (!pythonResponse.ok) {
      throw new Error(`Python API responded with status: ${pythonResponse.status}`);
    }

    const data = await pythonResponse.json();

    // Pass the unified payload straight back to your React frontend
    return NextResponse.json(data);

  } catch (error) {
    console.error("Next.js Assistant Route Error:", error);
    return NextResponse.json(
      { error: "Failed to communicate with the scheduling brain." }, 
      { status: 500 }
    );
  }
}