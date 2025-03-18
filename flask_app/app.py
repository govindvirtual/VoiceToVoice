from flask import Flask, jsonify, request 
from flask_restful import Resource, Api
  
# creating the flask app 
app = Flask(__name__) 
# creating an API object 
api = Api(app) 


class ValidateAudioLength(Resource):
    # POST request to handle validate audio length
    def post(self):
        try:
            data = request.json
            length = data.get("length", 0)
            text = data.get("text", "")

            if length > 60:
                # Trim the middle portion of the text to fit within 60 seconds
                words = text.split()
                mid = len(words) // 2
                trimmed_text = " ".join(words[mid-30:mid+30])  # Keep 60 words around the center
                return {"text": trimmed_text}, 200
            return {"text": text}, 200
        except Exception as e:
            return 400

  
  
# adding the defined resources along with their corresponding urls
api.add_resource(ValidateAudioLength, '/validate-audio-length')
  
  
# driver function
if __name__ == '__main__':
    app.run(debug = True)