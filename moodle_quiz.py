from quart import Quart, jsonify, request, render_template

app = Quart(__name__)


@app.route("/", methods=["GET"])
async def ping():
    return await render_template("home.html")


# Route pour récupérer des données avec un paramètre
@app.route("/data/<string:item>", methods=["GET"])
async def get_data(item):
    data = {"item_requested": item, "description": "Ceci est une description de l'item."}
    return jsonify(data), 200


# Route pour créer une nouvelle ressource via une requête POST
@app.route("/data", methods=["POST"])
async def create_data():
    body = await request.get_json()
    if "name" not in body:
        return jsonify({"error": "Nom requis"}), 400

    new_item = {"name": body["name"], "description": body.get("description", "Pas de description fournie.")}
    return jsonify(new_item), 201


if __name__ == "__main__":
    app.run()
