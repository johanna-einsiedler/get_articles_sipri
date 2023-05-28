from flask import Flask, render_template, request, url_for, flash, redirect
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
from bs4 import BeautifulSoup
import requests
import regex as re
from datetime import datetime, timedelta, date
import nltk
import spacy
import en_core_web_sm
import locationtagger
import dateutil.parser
import os
import threading

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from io import StringIO
import ssl

#pw Gmail: rt;NkCX7EA7k.jV

app = Flask(__name__)
app.config['SECRET_KEY'] = 'df0331cefc6c2b9a5d0208a726a5d1c0fd37324feba25507'

# dictionary to gather content 
content = {}
# initial keyword list
keywords_list = ['FMS','FMF', 'Foreign Military']

articles_display=[]


# function to do the website scraping
def scraper_function(from_date, keywords,email):
    # create output dataframe
    output = pd.DataFrame(columns =["date","country","keyword","paragraph","paragraph_num","URL"])
    # scrape first page for list of articles
    page_counter = 0
    while page_counter >=0:
        if page_counter == 0:
            # specify homepage URL
            url = "https://www.defense.gov/News/Contracts/"
            page_counter=2
        else:
            url = "https://www.defense.gov/News/Contracts/?Page="+str(page_counter)
            page_counter=page_counter+1
        print(url)
        # Send a GET request to the URL
        response = requests.get(url)
        # Create a BeautifulSoup object to parse the HTML content
        soup = BeautifulSoup(response.content, "html.parser")
        # extract urls of articles listed on this page
        articles = soup.find_all("listing-titles-only")

        # loop through articles 
        for anum, a in enumerate(articles):
            # check for publish date
            published = a["publish-date-ap"]
            published = dateutil.parser.parse(published)
            # check if article was published after the from date
            if (published.date()>from_date):
                print("Extracting Article from: ", published.date())
                articles_display.append(published.date())
                render_template('scrape.html', keywords=content['keywords'],articles=articles_display)
                article_url = a["article-url"]
                #article_url = "https://www.defense.gov/News/Contracts/Contract/Article/3391634/"
                # navigate to article page and extract html
                response_article = requests.get(article_url)
                soup_article = BeautifulSoup(response_article.content,"html.parser")
                # get date of article
                article_date = re.findall(r"\w+\s\d{1,2},\s\d{4}", soup_article.find_all("h1")[0].text)
                article_date = dateutil.parser.parse(article_date[0])
                # get all paragraphs of the article
                paragraphs = soup_article.find_all("p")
            # loop through paragraphs
                for pnum, p in enumerate(paragraphs):
                    ptext = p.text
                    # check for countries
                    try:
                        countries = locationtagger.find_locations(text = ptext).countries
                        countries = ", ".join(countries)
                    except:
                        countries = []
                    # check for keywords
                    words_found = []
                    for word in keywords:
                        if word.lower() in ptext.lower():
                            words_found.append(word)

                    if (len(countries) > 0 or len(words_found) > 0):
                        row = [article_date,countries,words_found,ptext,pnum-4,article_url]
                        row = pd.DataFrame([row], columns=output.columns)
                        output = pd.concat([output,row],ignore_index=True)

            else:
                page_counter = -1
        if page_counter != -1:
            print("Going to page number "+ str(page_counter))

        send_email(email,output)


def send_email(recipient,df):
    sender ='sipri.sipri.2023@gmail.com'
    pw ='iuflbpsyzaeyqrek'

     # Create the email
    msg = MIMEMultipart()
    msg['From'] = 'sipri.sipri.2023@gmail.com'
    msg['To'] = str(recipient)
    msg['Subject'] = 'Extracted Articles'

    context = ssl.create_default_context()
    # Convert the DataFrame to a CSV and save it to a StringIO object
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)

    csv_data = csv_buffer.getvalue().encode('utf-8')
    attachment = MIMEBase('application', 'octet-stream')
    attachment.set_payload(csv_data)
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', 'attachment', filename='dataframe.csv')
    msg.attach(attachment)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(sender, pw)
        smtp.sendmail(sender, recipient, msg.as_string())


# index page
@app.route('/', methods=('GET', 'POST'))
def index():
    if request.method == 'POST':
        return redirect(url_for('get_date'))
    return render_template('index.html')

@app.route('/get_date/', methods=('GET', 'POST'))
def get_date():
    if request.method == 'POST':
        input_date = request.form['input_date']
        # if no date was provided, default to one week prior to current date
        if not input_date:
            from_date = date.today() - timedelta(days=7)
            content['from_date']=from_date
            return redirect(url_for('keywords'))
        # else extract articles since the day the user chose
        else: 
            date_choice = input_date.lower()
            try:
                from_date = dateutil.parser.parse(date_choice)
                print("Extracting all articles published since "+ str(from_date.date()))
                content['from_date']=from_date.date()
                return redirect(url_for('keywords'))
            # if data format cannot be read, ask again
            except:
                ask_again = "Thats not a dateformat I can understand. Please write the date in the following format e.g. May 9, 2023"
                return render_template('get_date.html', ask_again = ask_again)
    return render_template('get_date.html')


@app.route('/keywords/', methods=('GET', 'POST'))
def keywords():
    if request.method == 'POST':
        keywords_new = request.form['keywords_new']
        # if no keywords are added stick with the original list
        if not keywords_new:
            content['keywords']=keywords_list
            return redirect(url_for('email'))
        # else add new keywords to list
        else:
            choice_keywords = keywords_new.lower()
            if len(choice_keywords)>0:
                keywords_list_new = keywords_list+choice_keywords.split(',')           
                content['keywords']=keywords_list_new
                return redirect(url_for('email'))
    return render_template('keywords.html', date=content['from_date'].strftime("%B %d, %Y"), keywords=keywords_list)

@app.route('/email/', methods=('GET', 'POST'))
def email():
    if request.method == 'POST':
        email_adress = request.form['email']
        content['email'] = email_adress
        scraper_function(content['from_date'],content['keywords'], content['email'])
        return redirect(url_for('scraping'))
    return render_template('email.html')


@app.route('/scrape/', methods=('GET', 'POST'))
def scraping():

    #threading.Thread(target=scraper_function(content['from_date'],content['keywords'])).start()
    #articles_display=[]
    #output = scraper_function(content['from_date'],content['keywords'])
    return render_template('scrape.html')
   