from flask import Flask, redirect, url_for, render_template
import time

#Updated this comment to test git commit

app = Flask(__name__, static_folder="static", template_folder="templates")

#Pages for expressions
@app.route("/")
def home():
    return render_template("index.html")


# if __name__ == '__main__':
#     app.run(debug=False, host='0.0.0.0', port=5000)