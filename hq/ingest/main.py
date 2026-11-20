"""
hq/ingest/main.py
FastAPI Regional Ingestion Service.
Run with REGION=in on port 8001 or REGION=eu on port 8002.
"""

import os
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from hq.ingest.service import process_ingest_payload


def create_ingest_app(region: str = "eu") -> FastAPI:
    app = FastAPI(title=f"Airlock Ingest ({region.upper()})")

    @app.get("/health")
    def health_check():
        return {"status": "ok", "region": region}

    @app.post("/ingest")
    async def ingest_payload(
        request: Request,
        x_airlock_guard_id: str = Header(None, alias="X-Airlock-Guard-ID"),
        x_airlock_signature: str = Header(None, alias="X-Airlock-Signature"),
        x_airlock_timestamp: str = Header(None, alias="X-Airlock-Timestamp"),
    ):
        raw_body = await request.body()
        status_code, result = process_ingest_payload(
            region=region,
            raw_body=raw_body,
            guard_id=x_airlock_guard_id,
            signature=x_airlock_signature,
            timestamp_str=x_airlock_timestamp,
        )
        if status_code != 200:
            raise HTTPException(status_code=status_code, detail=result.get("error", "Ingest error"))
        return JSONResponse(status_code=200, content=result)

    return app


# Default app instance loaded by uvicorn
default_region = os.getenv("REGION", "eu")
app = create_ingest_app(region=default_region)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002" if default_region == "eu" else "8001"))
    uvicorn.run("hq.ingest.main:app", host="0.0.0.0", port=port, reload=False)
