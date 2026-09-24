# Ledger — Invoice & Supplier Payment Tracker

## Local run
1. pip install -r requirements.txt
2. export ANTHROPIC_API_KEY=your-key-here
3. python app.py
4. Open http://localhost:5000

## Deploy
See deployment instructions provided separately. In short: set ANTHROPIC_API_KEY
and SECRET_KEY as environment variables on your host, then run with gunicorn:
  gunicorn -w 2 -b 0.0.0.0:$PORT app:app
