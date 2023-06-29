import datetime
import json
import random
from functools import wraps
import flask.scaffold
import jwt
import logging
import pika
import requests
import werkzeug
from bson import ObjectId
from flask import Flask, jsonify, g, request
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from pymongo import MongoClient
werkzeug.cached_property = werkzeug.utils.cached_property
flask.helpers._endpoint_from_view_func = flask.scaffold._endpoint_from_view_func

app = Flask(__name__)
CORS(app, methods=['DELETE', 'POST', 'PUT', 'GET', 'OPTIONS'])

SWAGGER_URL = '/swagger'
API_URL = '/static/swagger.json'
SWAGGERUI_BLUEPRINT = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "user-service"
    }
)
app.register_blueprint(SWAGGERUI_BLUEPRINT, url_prefix=SWAGGER_URL)


def generate_token(user_id, username):
    secret = 'nekaSkrivnost'
    payload = {
        'sub': user_id,
        'name': username,
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
    }
    token = jwt.encode(payload, secret, algorithm='HS256')
    return token


def verify_token(token):
    secret = 'nekaSkrivnost'
    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return 'Signature expired. Please log in again.'
    except jwt.InvalidTokenError:
        return 'Invalid token. Please log in again.'


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization'].split(" ")[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        data = verify_token(token)
        if isinstance(data, str):
            return jsonify({'message': 'Token is invalid!'}), 401
        g.user = data
        return f(*args, **kwargs)

    return decorated_function


client = MongoClient('mongodb://mongo:27017/user-service')
db = client['user-service']
users_collection = db['users']
admin_collection = db['admins']
counter_collection = db['counters']

app_name = 'user-service'

amqp_url = 'amqp://student:student123@studentdocker.informatika.uni-mb.si:5672/'
exchange_name = 'UPP-2'
queue_name = 'UPP-2'


def get_next_sequence_value(sequence_name):
    counter = counter_collection.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'value': 1}},
        upsert=True,
        return_document=True
    )
    return counter['value']


def json_encoder(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj


# GET /users
@app.route('/users', methods=['GET'])
def get_users():
    correlation_id = str(random.randint(1, 99999))
    users = list(users_collection.find().sort('_id', 1))
    users_json = json.dumps(users, default=json_encoder)
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET users*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()
    return jsonify(json.loads(users_json))


# GET /users/{id}
@app.route('/users/<string:user_id>', methods=['GET'])
@login_required
def get_user(user_id):
    correlation_id = str(random.randint(1, 99999))
    user = users_collection.find_one({'id': int(user_id)})
    if user:
        user_json = json.dumps(user, default=json_encoder)
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET one user*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(json.loads(user_json))
    else:
        return jsonify({'error': 'User not found'}), 404


# POST /users
@app.route('/users', methods=['POST'])
def create_user():
    correlation_id = str(random.randint(1, 99999))
    new_user = {
        'id': get_next_sequence_value('user_id'),
        'name': request.json.get('name'),
        'email': request.json.get('email'),
        'password': request.json.get('password'),
        'isAdmin': 'false'
    }
    result = users_collection.insert_one(new_user)
    new_user['_id'] = str(result.inserted_id)
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve POST one user*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()
    return jsonify(new_user), 201


# POST /admin
@app.route('/admins', methods=['POST'])
def create_admin():
    correlation_id = str(random.randint(1, 99999))
    new_user = {
        'id': get_next_sequence_value('user_id'),
        'name': request.json.get('name'),
        'email': request.json.get('email'),
        'password': request.json.get('password'),
        'isAdmin': 'true'
    }
    result = users_collection.insert_one(new_user)
    new_user['_id'] = str(result.inserted_id)
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve POST admin*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()
    return jsonify(new_user), 201


# PUT /users/{id}
@app.route('/users/<string:user_id>', methods=['PUT'])
def update_user(user_id):
    correlation_id = str(random.randint(1, 99999))
    user = users_collection.find_one({'id': int(user_id)})
    if user:
        user['name'] = request.json.get('name')
        user['email'] = request.json.get('email')
        users_collection.update_one({'id': int(user_id)}, {'$set': user})
        user_json = json.dumps(user, default=json_encoder)
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve PUT user data*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(json.loads(user_json))
    else:
        return jsonify({'error': 'User not found'}), 404


# PUT /users/{id}/password
@app.route('/users/<string:user_id>/password', methods=['PUT'])
def change_password(user_id):
    correlation_id = str(random.randint(1, 99999))
    user = users_collection.find_one({'id': int(user_id)})
    if user:
        user['password'] = request.json.get('password')
        users_collection.update_one({'id': int(user_id)}, {'$set': user})
        user_json = json.dumps(user, default=json_encoder)
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve PUT user password*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(json.loads(user_json))
    else:
        return jsonify({'error': 'User not found'}), 404


# DELETE /users/{id}
@app.route('/users/<string:user_id>', methods=['DELETE'])
def delete_user(user_id):
    correlation_id = str(random.randint(1, 99999))
    result = users_collection.delete_one({'id': int(user_id)})
    if result.deleted_count > 0:
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET users*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify({'message': 'User deleted'})
    else:
        return jsonify({'error': 'User not found'}), 404


# POST /users/login
@app.route('/users/login', methods=['POST'])
def login_user():
    correlation_id = str(random.randint(1, 99999))
    email = request.json.get('email')
    password = request.json.get('password')
    user = users_collection.find_one({'email': email, 'password': password})
    if user:
        token = generate_token(user['id'], user['name'])
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve POST user login*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify({'message': 'Login successful', 'token': token, 'id': user['id'], 'isAdmin': user['isAdmin']})
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


# POST /users/logout
@app.route('/users/logout', methods=['POST'])
def logout_user():
    correlation_id = str(random.randint(1, 99999))
    message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
        datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve POST logout*'))
    connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
    channel = connection.channel()

    channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
    channel.queue_declare(queue=queue_name)
    channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

    channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

    connection.close()
    return jsonify({'message': 'Logout successful'})


# GET /users/{id}/orders
@app.route('/users/<string:user_id>/orders', methods=['GET'])
def get_user_orders(user_id):
    correlation_id = str(random.randint(1, 99999))
    order_service_url = f'http://py-api:3000/orders?user_id={user_id}'
    headers = {'X-Correlation-ID': correlation_id}
    response = requests.get(order_service_url, headers=headers)

    if response.status_code == 200:
        orders = response.json()
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET user orders*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(orders)
    else:
        return jsonify({'error': 'Failed to retrieve user orders'}), response.status_code


# GET /users/{id}/notifications
@app.route('/users/<string:user_id>/notifications', methods=['GET'])
def get_user_notifications(user_id):
    correlation_id = str(random.randint(1, 99999))
    notification_service_url = f'http://py-api:7000/notifications?user_id={user_id}'
    headers = {'X-Correlation-ID': correlation_id}
    response = requests.get(notification_service_url, headers=headers)

    if response.status_code == 200:
        orders = response.json()
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET user notifications*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(orders)
    else:
        return jsonify({'error': 'Failed to retrieve user notifications.'}), response.status_code


# GET /menu
@app.route('/users/menu', methods=['GET'])
def get_user_menu():
    correlation_id = str(random.randint(1, 99999))
    menu_service_url = f'http://py-api:8000/menu/all'
    headers = {'X-Correlation-ID': correlation_id}
    response = requests.get(menu_service_url, headers=headers)

    if response.status_code == 200:
        orders = response.json()
        message = ('%s INFO %s Correlation: %s [%s] - <%s>' % (
            datetime.datetime.now(), request.url, correlation_id, app_name, '*Klic storitve GET menu*'))
        connection = pika.BlockingConnection(pika.URLParameters(amqp_url))
        channel = connection.channel()

        channel.exchange_declare(exchange=exchange_name, exchange_type='direct')
        channel.queue_declare(queue=queue_name)
        channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=queue_name)

        channel.basic_publish(exchange=exchange_name, routing_key=queue_name, body=message)

        connection.close()
        return jsonify(orders)
    else:
        return jsonify({'error': 'Failed to retrieve menu.'}), response.status_code


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
