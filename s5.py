from flask import Flask, request, redirect, render_template, url_for, send_file
import stripe
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Table, TableStyle
import io
import os


app = Flask(__name__, static_url_path="", static_folder="static")
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost:5432/paymentdetails'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USERNAME'] = 'valid email'
app.config['MAIL_PASSWORD'] = 'Password'
app.config['MAIL_DEFAULT_SENDER'] = 'valid email'
app.config['MAIL_DEBUG'] = True
app.config['SECRET_KEY'] = 'secret key'


db = SQLAlchemy(app)
mail = Mail(app)


stripe.api_key = "stripe secret key"
your_domain = "http://127.0.0.1:5000"

class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    plan = db.Column(db.String(50))
    subscription_id = db.Column(db.String(100))
    amount = db.Column(db.Integer)
    status = db.Column(db.String(20))
    customer_name = db.Column(db.String(100))
    customer_email = db.Column(db.String(100))
    current_period_start = db.Column(db.DateTime)
    current_period_end = db.Column(db.DateTime)
    payment_method = db.Column(db.String(100))


with app.app_context():
    db.create_all()

@app.route('/checkout')
def checkout():
    return render_template('checkout.html')

@app.route('/create_checkout_session', methods=['POST'])
def create_checkout_session():
    try:
        subscription_plan = request.form['subscription_plan']
        if subscription_plan == 'annual':
            price_id = 'Price Id'
        elif subscription_plan == 'daily':
            price_id = 'Price Id'
        else:
            price_id = 'Price Id'

        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': price_id,
                    'quantity': 1
                }
            ],
            mode='subscription',
            success_url=your_domain + "/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=your_domain + "/cancel",
        )

    except Exception as e:
        return str(e)
    return redirect(checkout_session.url, code=302)


@app.route('/success', methods=['GET'])
def success():
    session_id = request.args.get('session_id')

    if session_id:
        session = stripe.checkout.Session.retrieve(session_id)
        subscription_id = session.subscription
        subscription = stripe.Subscription.retrieve(subscription_id)
        customer_id = subscription.customer
        customer = stripe.Customer.retrieve(customer_id)
        price = stripe.Price.retrieve(subscription.plan.id)
        amount = price.unit_amount / 100
        plan = 'Daily' if subscription.plan.interval == 'day' else 'Monthly' if subscription.plan.interval == 'month' else 'Annual'

        subscription_details = Subscription(
            plan=plan,
            subscription_id=subscription.id,
            amount=amount,
            status=subscription.status,
            customer_name=customer.name,
            customer_email=customer.email,
            current_period_start=datetime.fromtimestamp(subscription.current_period_start),
            current_period_end=datetime.fromtimestamp(subscription.current_period_end),
            payment_method=subscription.default_payment_method
        )
        db.session.add(subscription_details)
        db.session.commit()

        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)

        # Background Image with reduced opacity
        background = ImageReader('static/Images/auto_intelli_logo_final.png')
        c.saveState()
        c.setFillAlpha(0.2)  # Set opacity to 30%
        c.drawImage(background, 150, 300, width=300, height=300)
        c.restoreState()

        # Adding Logo in the top left corner
        logo = ImageReader('static/Images/logo.jpg')
        c.drawImage(logo, 30, 750, width=100, height=50)


        # Adding Text
        c.setFont("Helvetica-Bold", 14)
        c.drawString(30, 720, "Thank you for subscribing Autointelli! Here are your subscription details")
        c.setFont("Helvetica-Bold", 14)
        c.drawString(30, 690, "Subscription Invoice")

        # Adding a Vertical Table for Subscription Details
        data = [
            ['Detail', 'Value'],
            ['Plan', plan],
            ['Subscription ID', subscription.id],
            ['Status', subscription.status],
            ['Customer Name', customer.name],
            ['Customer Email', customer.email],
            ['Amount', f"INR {amount}"],
            ['Period Start', datetime.fromtimestamp(subscription.current_period_start).strftime("%Y-%m-%d %H:%M:%S")],
            ['Period End', datetime.fromtimestamp(subscription.current_period_end).strftime("%Y-%m-%d %H:%M:%S")],
            ['Payment Method', subscription.default_payment_method]
        ]

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.transparent),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.transparent),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))

        # Increase table width and height
        table_width = 700
        table_height = 500

        table.wrapOn(c, table_width, table_height)
        table.drawOn(c, inch, 450,100)

        c.save()
        pdf_buffer.seek(0)

        pdf_filename = f"invoices/invoice_{subscription.id}.pdf"
        with open(pdf_filename, 'wb') as f:
            f.write(pdf_buffer.read())

        msg = Message("Subscription Details", recipients=[customer.email])
        msg.body = f"Thank you for subscribing!\n\nHere are your subscription details:\nPlan: {plan}\nSubscription ID: {subscription.id}\nStatus: {subscription.status}\nAmount: ₹{amount}\nCurrent Period Start: {datetime.fromtimestamp(subscription.current_period_start)}\nCurrent Period End: {datetime.fromtimestamp(subscription.current_period_end)}\nPayment Method: {subscription.default_payment_method}"
        with open(pdf_filename, 'rb') as fp:
            msg.attach("invoice.pdf", "application/pdf", fp.read())
        mail.send(msg)

        return render_template("success1.html", subscription_details=subscription_details, invoice_url=url_for('get_invoice', subscription_id=subscription.id))
    else:
        return "Invalid session ID"

@app.route('/invoice/<subscription_id>')
def get_invoice(subscription_id):
    pdf_filename = f"invoices/invoice_{subscription_id}.pdf"
    return send_file(pdf_filename, as_attachment=True)


@app.route('/cancel')
def cancel():
    return "Payment canceled"


if __name__ == '__main__':
    if not os.path.exists('invoices'):
        os.makedirs('invoices')
    app.run(debug=True, port=5000)
