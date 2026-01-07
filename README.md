# webapp_unified

PDF to PowerPoint 統合版Webアプリケーション

## 機能

- **Normal Mode**: AI (Gemini API) を使用してPDFを自動分析
- **JSON Mode**: 既存のJSONファイルを使用して変換
- JSONダウンロードステップ（メモリ制限対策）
- Standard/Safeguardモード選択

## セットアップ

```bash
pip install -r requirements.txt
```

## ローカル実行

```bash
# Windows
start_server.bat

# または
python server.py
```

環境変数 `GEMINI_API_KEY` を設定してNormalモードを使用

## ファイル構成

- `server.py` - FastAPIサーバー
- `static/` - フロントエンド
- `standalone_convert_v43_light_2x.py` - Standardモードコンバーター
- `standalone_convert_v4_v43_light_2x.py` - Safeguardモードコンバーター
