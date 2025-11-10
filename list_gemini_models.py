import requests

APIKEY = "AIzaSyBHugfi3WUXjILPdcZ6bxH2seCMf0dU144"

url = "https://generativelanguage.googleapis.com/v1beta/models"
params = {"key": APIKEY}
response = requests.get(url, params=params)
print(response.status_code)
print(response.text)
