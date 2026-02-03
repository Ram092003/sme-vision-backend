from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import pandas as pd
import io
import pdfplumber
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from database import SessionLocal, engine
from models import Base, Transaction


app = FastAPI(title="SME Financial Health API")

Base.metadata.create_all(bind=engine)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow Netlify + all
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {"status": "Backend running fine ✅"}


@app.post("/analyze/final-report")
async def analyze_financials(file: UploadFile = File(...)):

    contents = await file.read()
    filename = file.filename.lower()

    
    if filename.endswith(".csv"):
        df = pd.read_csv(io.StringIO(contents.decode("utf-8")))

    elif filename.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")

    elif filename.endswith(".pdf"):
        text_data = []
        with pdfplumber.open(io.BytesIO(contents)) as pdf:
            for page in pdf.pages:
                text_data.append(page.extract_text())
        text = "\n".join(text_data)
        df = pd.read_csv(io.StringIO(text))

    else:
        return {"error": "Unsupported file format"}

   
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["type"] = df["type"].str.lower().str.strip()
    df["date"] = pd.to_datetime(df["date"])

    
    db: Session = SessionLocal()
    for _, row in df.iterrows():
        db.add(Transaction(
            date=row["date"],
            industry=row.get("industry", "General"),
            category=row.get("category", "General"),
            amount=float(row["amount"]),
            type=row["type"]
        ))
    db.commit()
    db.close()

    # ---------- METRICS ----------
    total_income = float(df[df["type"] == "income"]["amount"].sum())
    total_expense = float(df[df["type"] == "expense"]["amount"].sum())
    net_profit = total_income - total_expense
    profit_margin = round((net_profit / total_income) * 100, 2) if total_income > 0 else 0

    # ---------- RISK ----------
    if net_profit <= 0:
        risk = "HIGH"
    elif profit_margin < 5:
        risk = "MEDIUM"
    else:
        risk = "LOW"

    # ---------- CREDIT ----------
    credit = 50
    if net_profit > 0:
        credit += 20
    if profit_margin > 10:
        credit += 15
    credit = min(100, credit)

    # ---------- MONTHLY ----------
    df["month"] = df["date"].dt.to_period("M").astype(str)
    monthly = df.groupby(["month", "type"])["amount"].sum().unstack().fillna(0)
    monthly["cashflow"] = monthly.get("income", 0) - monthly.get("expense", 0)

    # ---------- LOAN ----------
    eligibility = "YES" if credit >= 75 else "MAYBE" if credit >= 55 else "NO"
    avg_profit = net_profit / max(len(monthly), 1)
    multiplier = 12 if risk == "LOW" else 6 if risk == "MEDIUM" else 3

    loan = {
        "eligible": eligibility,
        "recommended_amount": int(avg_profit * multiplier) if eligibility != "NO" else 0,
        "tenure_months": 24 if risk == "LOW" else 18,
        "interest_rate_estimate": "10–12%" if risk == "LOW" else "13–16%",
        "risk_level": risk,
        "confidence_score": credit
    }

    return {
        "investor_metrics": {
            "total_income": total_income,
            "total_expense": total_expense,
            "net_profit": net_profit,
            "profit_margin_percent": profit_margin,
            "credit_score": credit
        },
        "monthly_cashflow": monthly.reset_index().to_dict(orient="records"),
        "loan_recommendation": loan,
        "ai_summary": {
            "english": f"Business earned ₹{total_income:,.0f}, profit ₹{net_profit:,.0f}. Loan eligibility {eligibility}.",
            "tamil": f"மொத்த வருமானம் ₹{total_income:,.0f}. கடன் தகுதி: {eligibility}.",
            "hindi": f"कुल आय ₹{total_income:,.0f}. ऋण पात्रता: {eligibility}."
        }
    }


@app.post("/download-pdf")
async def download_pdf(data: dict):

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "SME Financial Health Report")

    c.setFont("Helvetica", 12)
    y -= 40

    for k, v in data["investor_metrics"].items():
        c.drawString(50, y, f"{k.replace('_',' ').title()}: {v}")
        y -= 18

    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, y, "Loan Recommendation")
    y -= 20

    for k, v in data["loan_recommendation"].items():
        c.drawString(50, y, f"{k.replace('_',' ').title()}: {v}")
        y -= 15

    c.save()
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=SME_Report.pdf"}
    )

