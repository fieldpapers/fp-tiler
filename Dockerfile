FROM node:22

RUN useradd -ms /bin/bash fieldpapers
RUN mkdir -p /home/fieldpapers/app && chown -R fieldpapers:fieldpapers /home/fieldpapers/app

USER fieldpapers

WORKDIR /home/fieldpapers/app
ADD . /home/fieldpapers/app/

RUN npm install

VOLUME ["/home/fieldpapers/app"]
EXPOSE 8080

CMD npm start
