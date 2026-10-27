
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/about")
def about():
    return """
    <h1>このサイトについて</h1>
    <p>PythonとFlaskで作ったサイトです。</p>
    <a href="/">トップに戻る</a>
    """

if __name__ == "__main__":
    app.run(debug=True)
