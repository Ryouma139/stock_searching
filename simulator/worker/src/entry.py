"""シミュレーション条件を D1 に保存・一覧取得する Python Worker（任意・雛形）。

  GET  /api/scenarios   最新 50 件
  POST /api/scenarios   {"title","mode","ticker","annual_rate","initial","monthly","years","final_value"}

Python Workers はまだ仕様変更が多いので、デプロイ前に公式ドキュメントで API を確認すること。
"""
import json
from urllib.parse import urlparse

from workers import Response, WorkerEntrypoint

HEADERS = {
    "content-type": "application/json; charset=utf-8",
    "access-control-allow-origin": "*",  # 本番は Pages のドメインに絞る
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type",
}


def json_response(data, status=200):
    return Response(json.dumps(data, ensure_ascii=False), status=status, headers=HEADERS)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        path = urlparse(request.url).path
        if request.method == "OPTIONS":
            return Response("", headers=HEADERS)
        if path != "/api/scenarios":
            return json_response({"error": "not found"}, 404)

        if request.method == "GET":
            result = await self.env.DB.prepare(
                "SELECT * FROM scenarios ORDER BY created_at DESC LIMIT 50"
            ).all()
            return json_response(result.results.to_py())

        if request.method == "POST":
            body = json.loads(await request.text())
            if body.get("mode") not in ("fixed", "historical") or not body.get("title"):
                return json_response({"error": "invalid input"}, 400)
            await self.env.DB.prepare(
                "INSERT INTO scenarios (title, mode, ticker, annual_rate, initial, monthly, years, final_value)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ).bind(
                str(body["title"])[:100],
                body["mode"],
                body.get("ticker"),
                float(body.get("annual_rate", 0.10)),
                int(body.get("initial", 0)),
                int(body.get("monthly", 0)),
                int(body.get("years", 1)),
                body.get("final_value"),
            ).run()
            return json_response({"ok": True}, 201)

        return json_response({"error": "method not allowed"}, 405)
