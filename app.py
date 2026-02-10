from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
from functools import wraps
from dotenv import load_dotenv
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))

# Initialize Firebase Admin SDK
# Try loading from ENV string (for hosting) or from local file
firebase_creds_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
if firebase_creds_json:
    # If key is provided as a JSON string in environment variable
    cred_dict = json.loads(firebase_creds_json)
    cred = credentials.Certificate(cred_dict)
else:
    # Fallback to local file
    cred_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', 'serviceAccountKey.json')
    cred = credentials.Certificate(cred_path)

firebase_admin.initialize_app(cred)
db = firestore.client()

# Middleware for Role-Based Access Control
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'admin':
            return redirect(url_for('index')) # Or unauthorized page
        return f(*args, **kwargs)
    return decorated_function

def farmer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'farmer':
            return redirect(url_for('index'))
        # Check if approved
        if session.get('status') != 'approved':
             return render_template('farmer/pending.html')
        return f(*args, **kwargs)
    return decorated_function

def customer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session or session['role'] != 'customer':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Auth happens on client side with Firebase JS SDK
        # We receive the ID token to verify and set session
        id_token = request.json.get('idToken')
        try:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token['uid']
            
            # Get user role from Firestore
            user_ref = db.collection('users').document(uid)
            user_doc = user_ref.get()
            
            if user_doc.exists:
                user_data = user_doc.to_dict()
                session['user_id'] = uid
                session['role'] = user_data.get('role')
                session['status'] = user_data.get('status', 'active') # Farmers might be pending
                return jsonify({'status': 'success', 'role': session['role']})
            else:
                return jsonify({'status': 'error', 'message': 'User not found in database'})
                
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)})
            
    return render_template('login.html')

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/setup-admin')
@login_required
def setup_admin():
    uid = session['user_id']
    db.collection('users').document(uid).update({'role': 'admin'})
    session['role'] = 'admin'
    return redirect(url_for('admin_dashboard'))

@app.route('/seed-data')
def seed_data():
    uid = session.get('user_id', 'system_gen')
    role = session.get('role', 'admin')
    
    # If a farmer seeds, they own the products
    farmer_id = uid if role == 'farmer' else 'system_gen'
    
    products = [
        {
            "name": "Organic Red Tomatoes",
            "category": "Vegetables",
            "price": 45.0,
            "quantity": 150,
            "image_url": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80",
            "farmer_name": "Kumar Farms",
            "farmer_id": farmer_id,
            "status": "available",
            "createdAt": firestore.SERVER_TIMESTAMP
        },
        {
            "name": "Fresh Alphonso Mangoes",
            "category": "Fruits",
            "price": 120.0,
            "quantity": 60,
            "image_url": "https://images.unsplash.com/photo-1553279768-865429fa0078?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80",
            "farmer_name": "Salem Orchard",
            "farmer_id": farmer_id,
            "status": "available",
            "createdAt": firestore.SERVER_TIMESTAMP
        },
        {
            "name": "Basmati Rice (Premium)",
            "category": "Grains",
            "price": 85.0,
            "quantity": 500,
            "image_url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80",
            "farmer_name": "Punjab Grains",
            "farmer_id": farmer_id,
            "status": "available",
            "createdAt": firestore.SERVER_TIMESTAMP
        },
        {
            "name": "Farm Fresh Milk",
            "category": "Dairy",
            "price": 50.0,
            "quantity": 100,
            "image_url": "https://images.unsplash.com/photo-1550583724-125581f77033?ixlib=rb-1.2.1&auto=format&fit=crop&w=800&q=80",
            "farmer_name": "Green Dairy",
            "farmer_id": farmer_id,
            "status": "available",
            "createdAt": firestore.SERVER_TIMESTAMP
        }
    ]
    
    for p in products:
        db.collection('products').add(p)
        
    return "Marketplace seeded! Go back to <a href='/customer/dashboard'>Dashboard</a>."

# Admin Routes
@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Fetch Pending Farmers
    pending_farmers_ref = db.collection('users').where('role', '==', 'farmer').where('status', '==', 'pending').stream()
    pending_farmers = [{'id': doc.id, **doc.to_dict()} for doc in pending_farmers_ref]

    # Fetch Total Counts (This is a bit expensive in Firestore, usually we use counters, but for MVP direct count is fine)
    # Optimized: Use aggregation queries if available, or just stream for small datasets
    farmers_count = len(list(db.collection('users').where('role', '==', 'farmer').stream()))
    consumers_count = len(list(db.collection('users').where('role', '==', 'customer').stream()))
    products_count = len(list(db.collection('products').stream()))
    orders_count = len(list(db.collection('orders').stream()))

    counts = {
        'farmers': farmers_count,
        'consumers': consumers_count,
        'products': products_count,
        'orders': orders_count,
        'pending': len(pending_farmers)
    }
    return render_template('admin/dashboard.html', counts=counts, pending_farmers=pending_farmers)

@app.route('/admin/verify_farmer/<uid>/<action>')
@login_required
@admin_required
def verify_farmer(uid, action):
    user_ref = db.collection('users').document(uid)
    if action == 'approve':
        user_ref.update({'status': 'approved'})
    elif action == 'reject':
        user_ref.update({'status': 'rejected'}) # or delete
    return redirect(url_for('admin_dashboard'))

# Farmer Routes
@app.route('/farmer/dashboard')
@login_required
@farmer_required
def farmer_dashboard():
    # Fetch Farmer Stats
    uid = session['user_id']
    products = list(db.collection('products').where('farmer_id', '==', uid).stream())
    
    # Fetch real orders where farmer_id == uid
    orders_ref = db.collection('orders').where('farmer_id', '==', uid).stream()
    orders = [{'id': doc.id, **doc.to_dict()} for doc in orders_ref]
    
    total_sales = sum(float(order.get('total_price', 0)) for order in orders)
    
    stats = {
        'products': len(products),
        'orders': len(orders),
        'sales': total_sales
    }
    return render_template('farmer/dashboard.html', stats=stats)

@app.route('/farmer/orders')
@login_required
@farmer_required
def farmer_orders():
    uid = session['user_id']
    orders_ref = db.collection('orders').where('farmer_id', '==', uid).stream()
    orders = [{'id': doc.id, **doc.to_dict()} for doc in orders_ref]
    orders.sort(key=lambda x: x.get('createdAt').timestamp() if x.get('createdAt') and hasattr(x.get('createdAt'), 'timestamp') else 0, reverse=True)
    return render_template('farmer/orders.html', orders=orders)

@app.route('/api/update-order-status', methods=['POST'])
@login_required
@farmer_required
def update_order_status():
    try:
        data = request.json
        oid = data.get('order_id')
        new_status = data.get('status')
        
        db.collection('orders').document(oid).update({
            'delivery_status': new_status
        })
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/farmer/add-product', methods=['GET', 'POST'])
@login_required
@farmer_required
def add_product():
    if request.method == 'POST':
        # Handling product addition via backend form or JS fetch
        # If using standard form submission (easier for files if handled by server, but we use Firebase Storage mainly)
        # We'll use client-side JS to upload image and then send data to backend or just save directly from JS
        # BUT user wanted "Python Backend". So we should receive data here.
        # However, file upload handling is easier on client with Firebase Storage or server with Flask.
        # Let's use Flask for form data and save to Firestore. 
        # For Image, we'll accept a URL (uploaded via client JS to Firebase Storage first) OR simplest:
        # Just use client-side logic in the template to write to Firestore directly for consistency with Auth?
        # No, "Farmer Add Product Page" usually implies a backend route.
        # Let's support both. I'll implement the route to render the page, and the page will use JS to save to DB 
        # because saving file to Firebase Storage from Flask requires sending file to server first.
        # Client-side upload is better for performance.
        pass
    return render_template('farmer/add_product.html')

@app.route('/farmer/products')
@login_required
@farmer_required
def manage_products():
    uid = session['user_id']
    products_ref = db.collection('products').where('farmer_id', '==', uid).stream()
    products = [{'id': doc.id, **doc.to_dict()} for doc in products_ref]
    return render_template('farmer/products.html', products=products)

@app.route('/farmer/delete-product/<pid>')
@login_required
@farmer_required
def delete_product(pid):
    db.collection('products').document(pid).delete()
    return redirect(url_for('manage_products'))

# Customer / Marketplace Routes
@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    # Fetch all available products
    products_ref = db.collection('products').where('status', '==', 'available').stream()
    all_products = [{'id': doc.id, **doc.to_dict()} for doc in products_ref]
    
    # Group products by name for Consensus Pricing
    grouped = {}
    for p in all_products:
        name = p['name'].strip().lower()
        if name not in grouped:
            grouped[name] = {
                'display_name': p['name'],
                'category': p['category'],
                'image_url': p['image_url'],
                'prices': [],
                'total_qty': 0
            }
        grouped[name]['prices'].append(p['price'])
        grouped[name]['total_qty'] += p['quantity']
    
    marketplace_products = []
    for key, data in grouped.items():
        avg_price = sum(data['prices']) / len(data['prices'])
        marketplace_products.append({
            'name': data['display_name'],
            'category': data['category'],
            'image_url': data['image_url'],
            'price': round(avg_price, 2),
            'quantity': data['total_qty'],
            'is_grouped': len(data['prices']) > 1
        })
        
    return render_template('customer/dashboard.html', products=marketplace_products)

@app.route('/customer/product/<name>')
@login_required
@customer_required
def product_details(name):
    # Search for products with this name
    products_ref = db.collection('products').where('status', '==', 'available').stream()
    matches = [doc.to_dict() for doc in products_ref if doc.to_dict()['name'].lower() == name.lower()]
    
    if not matches:
        return redirect(url_for('customer_dashboard'))
        
    avg_price = sum(p['price'] for p in matches) / len(matches)
    total_qty = sum(p['quantity'] for p in matches)
    
    product_data = {
        'name': matches[0]['name'],
        'category': matches[0]['category'],
        'image_url': matches[0]['image_url'],
        'price': round(avg_price, 2),
        'quantity': total_qty,
        'farmer_count': len(matches)
    }
    
    return render_template('customer/product_details.html', product=product_data)

@app.route('/customer/checkout/<name>', methods=['GET'])
@login_required
@customer_required
def checkout(name):
    # Find all farmers with this product
    products_ref = db.collection('products').where('status', '==', 'available').stream()
    matches = [doc.to_dict() for doc in products_ref if doc.to_dict()['name'].lower() == name.lower()]
    
    if not matches:
        return redirect(url_for('customer_dashboard'))
        
    avg_price = sum(p['price'] for p in matches) / len(matches)
    total_qty = sum(p['quantity'] for p in matches)
    
    product_data = {
        'id': 'grouped', # Backend will find the best farmer during placement
        'name': matches[0]['name'],
        'category': matches[0]['category'],
        'image_url': matches[0]['image_url'],
        'price': round(avg_price, 2),
        'quantity': total_qty
    }
    
    return render_template('customer/checkout.html', product=product_data)
    
@app.route('/customer/my-orders')
@login_required
@customer_required
def my_orders():
    uid = session['user_id']
    orders_ref = db.collection('orders').where('customer_id', '==', uid).stream()
    orders = [{'id': doc.id, **doc.to_dict()} for doc in orders_ref]
    # Sort using timestamp to avoid TypeError between datetime and int
    orders.sort(key=lambda x: x.get('createdAt').timestamp() if x.get('createdAt') and hasattr(x.get('createdAt'), 'timestamp') else 0, reverse=True)
    return render_template('customer/orders.html', orders=orders)

@app.route('/customer/track-order/<oid>')
@login_required
@customer_required
def track_order(oid):
    order_ref = db.collection('orders').document(oid).get()
    if order_ref.exists:
        order = {'id': order_ref.id, **order_ref.to_dict()}
        return render_template('customer/tracking.html', order=order)
    return redirect(url_for('my_orders'))

# Farmer Forum
@app.route('/farmer/forum')
@login_required
@farmer_required
def farmer_forum():
    # Fetch posts
    posts_ref = db.collection('forum_posts').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
    posts = [{'id': doc.id, **doc.to_dict()} for doc in posts_ref]
    return render_template('farmer/forum.html', posts=posts)

@app.route('/customer/add-review/<oid>', methods=['GET'])
@login_required
@customer_required
def add_review(oid):
    order_ref = db.collection('orders').document(oid).get()
    if order_ref.exists:
        order = {'id': order_ref.id, **order_ref.to_dict()}
        # Check if already reviewed (optional optimization)
        return render_template('customer/add_review.html', order=order)
    return redirect(url_for('my_orders'))

# Admin Review Monitoring
@app.route('/admin/reviews')
@login_required
@admin_required
def admin_reviews():
    reviews_ref = db.collection('reviews').order_by('createdAt', direction=firestore.Query.DESCENDING).stream()
    reviews = [{'id': doc.id, **doc.to_dict()} for doc in reviews_ref]
    return render_template('admin/reviews.html', reviews=reviews)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users_ref = db.collection('users').stream()
    users = [{'id': doc.id, **doc.to_dict()} for doc in users_ref]
    return render_template('admin/users.html', users=users)

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products_ref = db.collection('products').stream()
    products = [{'id': doc.id, **doc.to_dict()} for doc in products_ref]
    return render_template('admin/products.html', products=products)

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    orders_ref = db.collection('orders').stream()
    orders = [{'id': doc.id, **doc.to_dict()} for doc in orders_ref]
    # Sort using timestamp to avoid TypeError
    orders.sort(key=lambda x: x.get('createdAt').timestamp() if x.get('createdAt') and hasattr(x.get('createdAt'), 'timestamp') else 0, reverse=True)
    return render_template('admin/orders.html', orders=orders)

@app.route('/api/admin/update-price', methods=['POST'])
@login_required
@admin_required
def admin_update_price():
    try:
        data = request.json
        pid = data.get('product_id')
        new_price = float(data.get('price'))
        db.collection('products').document(pid).update({'price': new_price})
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API Routes for Data Operations (Bypassing Client Security Rules)
@app.route('/api/register-user-data', methods=['POST'])
def register_user_data():
    try:
        data = request.json
        uid = data.get('uid')
        # Use Admin SDK to write to Firestore
        db.collection('users').document(uid).set({
            'email': data.get('email'),
            'role': data.get('role'),
            'name': data.get('name'),
            'status': 'pending' if data.get('role') == 'farmer' else 'active',
            'address': data.get('address', ''),
            'contact': data.get('contact', ''),
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/add-product', methods=['POST'])
@login_required
@farmer_required
def api_add_product():
    try:
        data = request.json
        uid = session['user_id']
        # Use Admin SDK - simple and secure
        db.collection('products').add({
            'farmer_id': uid,
            'farmer_name': data.get('farmer_name', 'Farmer'),
            'name': data.get('name'),
            'category': data.get('category'),
            'price': float(data.get('price')),
            'quantity': int(data.get('quantity')),
            'image_url': data.get('image_url'),
            'status': 'available',
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/place-order', methods=['POST'])
@login_required
@customer_required
def api_place_order():
    try:
        data = request.json
        uid = session['user_id']
        product_name = data.get('product_name')
        req_qty = int(data.get('quantity'))
        
        # Find all farmers with this product
        products_ref = db.collection('products').where('status', '==', 'available').stream()
        all_matches = []
        for doc in products_ref:
            p = doc.to_dict()
            p['id'] = doc.id
            if p['name'].lower() == product_name.lower():
                all_matches.append(p)
        
        if not all_matches:
            return jsonify({'status': 'error', 'message': 'Product no longer available'}), 404
            
        # Sort by price ascending to pick the cheapest farmer (Consensus Fulfillment)
        all_matches.sort(key=lambda x: x['price'])
        
        target_product = None
        for p in all_matches:
            if p['quantity'] >= req_qty:
                target_product = p
                break
        
        if not target_product:
             return jsonify({'status': 'error', 'message': 'Individual farmers do not have enough stock for this quantity.'}), 400

        # Create Order (Customer pays the average price they saw, but order goes to cheapest farmer)
        db.collection('orders').add({
            'customer_id': uid,
            'customer_name': data.get('customer_name'),
            'farmer_id': target_product['farmer_id'],
            'product_id': target_product['id'],
            'product_name': target_product['name'],
            'quantity': req_qty,
            'total_price': float(data.get('total_price')), # The avg price * qty
            'status': 'paid',
            'delivery_status': 'processing',
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        
        # Deduct Stock
        new_qty = target_product['quantity'] - req_qty
        db.collection('products').document(target_product['id']).update({'quantity': new_qty})
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/add-review', methods=['POST'])
@login_required
@customer_required
def api_add_review():
    try:
        data = request.json
        uid = session['user_id']
        db.collection('reviews').add({
            'customer_id': uid,
            'customer_name': data.get('customer_name'),
            'product_id': data.get('product_id'),
            'product_name': data.get('product_name'),
            'rating': int(data.get('rating')),
            'comment': data.get('comment'),
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/add-post', methods=['POST'])
@login_required
@farmer_required
def api_add_post():
    try:
        data = request.json
        uid = session['user_id']
        db.collection('forum_posts').add({
            'author_id': uid,
            'author_name': data.get('author_name'),
            'topic': data.get('topic'),
            'message': data.get('message'),
            'createdAt': firestore.SERVER_TIMESTAMP
        })
        return jsonify({'status': 'success'})
    except Exception as e:
         return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
