# -*- coding: utf-8 -*-
"""
Created on Sun Oct 22 16:37:14 2023

@author: psyfi
"""

from flask import Flask, render_template, request, redirect, url_for
import socket
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/', methods=['POST'])
def upload_file():
    uploaded_file = request.files['file']
    if uploaded_file.filename != '':
        uploaded_file.save(uploaded_file.filename)
    return redirect(url_for('index'))

if __name__ == "__main__":
    ## getting the hostname by socket.gethostname() method
    hostname = socket.gethostname()
    ## getting the IP address using socket.gethostbyname() method
    ip_address = socket.gethostbyname(hostname)
    ## printing the hostname and ip_address
    print(f"Hostname: {hostname}")
    print(f"IP Address: {ip_address}")
    
    pipeline_ip = requests.get('https://checkip.amazonaws.com').text.strip()
    print(f"IP Address: {pipeline_ip}")
    #from waitress import serve
    #serve(app,host=ip_address, port=8080)       
    #serve(app,host=ip_address, port=80)       
    #app.run()
    app.run(host='0.0.0.0', port=80)