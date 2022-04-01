from inspect import ArgSpec
import os, logging, coloredlogs, random
from flask import Flask, render_template, jsonify, request, Response, url_for
from flask_pymongo import PyMongo
from bson.json_util import dumps
from datetime import datetime


logger = logging.getLogger(__name__)
coloredlogs.install(level='DEBUG')
coloredlogs.install("INFO", logger=logger, fmt='%(asctime)s.%(msecs)03d [%(name)s] : %(message)s')
logging.info("INITIALIZING APP ...")
app = Flask(__name__)

if not os.getenv('MONGO_URI'):
    logging.exception("URI FROM MONGO NOT FOUND, EXITING ...")
    exit()

app.config["MONGO_URI"] = os.getenv('MONGO_URI')
mongo = PyMongo(app)
logging.info("ESTABLISHED CONNECTION TO DB")

@app.route('/', methods=['GET','POST'])
def home_page():
    """HOME PAGE, by rendering template"""
    return render_template('index.html')

"""
SAMPLE DATA GENERATION
cat_list = ['g', 'a', 'u', 't', 'm']
for xx in range(20):
    sample_data += [{'book name': 'name'+str(xx+1).zfill(2), 'category': random.choice(cat_list),'rent per day': random.randint(1, 4)}]

"""

@app.route("/push_into_db", methods=['POST'])
def push_into_db():
    """PUSHES SAMPLE DATA INTO DB"""
    sample_data = [
        {'book name': 'name01', 'category': 'g', 'rent per day': 4}, 
        {'book name': 'name02', 'category': 'm', 'rent per day': 2}, 
        {'book name': 'name03', 'category': 'a', 'rent per day': 3}, 
        {'book name': 'name04', 'category': 'm', 'rent per day': 4}, 
        {'book name': 'name05', 'category': 'g', 'rent per day': 3}, 
        {'book name': 'name06', 'category': 'a', 'rent per day': 1}, 
        {'book name': 'name07', 'category': 'u', 'rent per day': 1}, 
        {'book name': 'name08', 'category': 'u', 'rent per day': 3}, 
        {'book name': 'name09', 'category': 'm', 'rent per day': 3}, 
        {'book name': 'name10', 'category': 'g', 'rent per day': 3}, 
        {'book name': 'name11', 'category': 't', 'rent per day': 1}, 
        {'book name': 'name12', 'category': 'u', 'rent per day': 4}, 
        {'book name': 'name13', 'category': 't', 'rent per day': 2}, 
        {'book name': 'name14', 'category': 't', 'rent per day': 3}, 
        {'book name': 'name15', 'category': 't', 'rent per day': 2}, 
        {'book name': 'name16', 'category': 'u', 'rent per day': 1}, 
        {'book name': 'name17', 'category': 'm', 'rent per day': 3}, 
        {'book name': 'name18', 'category': 'g', 'rent per day': 2}, 
        {'book name': 'name19', 'category': 'm', 'rent per day': 3}, 
        {'book name': 'name20', 'category': 'm', 'rent per day': 2}
    ]
    mongo.db.books.insert_many(sample_data)
    return Response("DATA ADDED INTO DB", status=200)

@app.route("/list_books", methods=['GET'])
def list_books():
    """LISTS BOOKS ACCORDING TO PARAMS"""
    hit_list, args = [], args
    if "book name" in args:
        if "category" in args:
            if not 'low' in args and not 'high' in args:
                return Response("PARAM(s) low & high, MISSING IN REQ.", status=400)    

            for x in mongo.db.books.find({"book name":{'$regex':args['book name']},'category':args['category'],'rent per day':{ '$gte':int(args['low']), '$lte':int(args['high'])}}):
                x.pop('_id')
                hit_list += [x]
        else: 
            for x in mongo.db.books.find({"book name":{'$regex':args['book name']}}):
                x.pop('_id')
                hit_list += [x]
    else:
        if not 'low' in args and not 'high' in args:
            return Response( "PARAM(s) low & high, MISSING IN REQ.", status=400)
        for x in mongo.db.books.find({'rent per day':{ '$gte':int(args['low']), '$lte':int(args['high'])}}):
            x.pop('_id')
            hit_list += [x]

    return dumps(hit_list, indent=2)

@app.route("/issue_book", methods=['POST'])
def issue_book():
    """TRANSACTION RECORD OF BOOK ISSUING"""
    if not 'book name' in request.json and not 'person name' in request.json and not "issue date" in request.json:
        return Response("PARAM(s) 'book name' 'person name' 'issue date', MISSING IN REQ.", status=400)

    try:
        new_date = datetime.fromisoformat(request.json["issue date"])
    except ValueError:
        return Response("UNABLE TO PARSE DATE", status=400)

    issue_payload = {
        'book name': request.json["book name"],
        'person name': request.json['person name'],
        'issue date': new_date,
    }
    mongo.db.transaction.insert_one(issue_payload)
    return Response("BOOK ISSUE TRANSACTION RECORDED", status=200)

@app.route("/return_book",methods=['POST'])
def return_book():
    """TRANSACTION ISSUE OF BOOK RETURNING"""
    if not 'book name' in request.json and not 'person name' in request.json and not "return date" in request.json:
        return Response("PARAM(s) 'book name' 'person name' 'return date', MISSING IN REQ.", status=400)
    try:
        new_date = datetime.fromisoformat(request.json["return date"])
    except ValueError:
        return Response("UNABLE TO PARSE DATE", status=400)

    trnsctn = mongo.db.transaction.find_one({'book name':request.json["book name"], 'person name':request.json["person name"]})
    if trnsctn == None:
        return Response("RECORD NOT FOUND", status=400)

    delta = datetime.fromisoformat(request.json["return date"]) - trnsctn['issue date']
    book_cost = mongo.db.books.find_one({"book name":request.json["book name"]})
    total_cost = delta.days*book_cost['rent per day']
    mongo.db.transaction.update_one(trnsctn,{"$set":{'return_book':new_date,'rent':total_cost}}, upsert=True)
    return Response("BOOK RETURN TRANSACTION RECORDED", status=200)

@app.route("/book_status_by_ppl", methods=["GET"])
def book_status_by_ppl():
    """GET STATUS OF BOOK IN RELATED WITH PPL"""
    args, ctr, present_issue =  request.args, 0, []
    if not "book name" in args:
        return Response("PARAM(s) 'book name', MISSING IN REQ.", status=400)
  
    trnsctn = mongo.db.transaction.find({'book name':args["book name"]})
    for ii in trnsctn:
        if "return_book" in ii: ctr+=1
        else: present_issue.append(ii["person name"])
    return jsonify(total_no_of_ppl_issued=ctr, currently_issued=present_issue)

@app.route("/rent_genrtd",methods=["GET"])
def rent_genrtd():
    """GET TOTAL RENT GENERATED BY BOOK"""
    args, total_rent = request.args, 0
    if not "book name" in args:
        return Response("PARAM(s) 'book name', MISSING IN REQ.", status=400)  

    trnsctn = mongo.db.transaction.find({'book name':args["book name"]})
    for ii in trnsctn:
        if 'rent' in ii:
            total_rent += ii['rent']
    return jsonify(rent=total_rent)

@app.route("/list_books_issued",methods=["GET"])
def list_books_issued():
    """GET INFO OF BOOKS TAKEN BY PERSON"""
    args, books_issued = request.args, []
    if not "person name" in args:
        return Response("PARAM(s) 'person name', MISSING IN REQ.", status=400)  

    trans = mongo.db.transaction.find({'person name':args["person name"]})
    for ii in trans: books_issued.append(ii['book name'])
    return jsonify(books_issued_to_person=books_issued)

@app.route("/date_range", methods=["GET"])
def date_range():
    """GET INFO OF BOOKS ISSUED IN DATE RANGE"""
    args = request.args
    if not "end_date" in args and not "start_date" in args:
        return Response("Not enough parmeters", status=400)
    try:
        end_date = datetime.fromisoformat(args["end_date"])
    except ValueError:
        return Response("UNABLE TO PARSE DATE", status=400)

    try:
        start_date = datetime.fromisoformat(args["start_date"])
    except ValueError:
        return Response("UNABLE TO PARSE DATE", status=400)

    trnsctn = mongo.db.transaction.find({'issue date':{'$gte':start_date,'$lte':end_date }})
    list_books = []
    for ii in trnsctn:
        list_books.append({'book name':ii['book name'], 'issued person':ii['person name']})
    return jsonify(books_issued=list_books)
    

if __name__ == '__main__':
    app.run(debug=True, threaded=True, port=5000)