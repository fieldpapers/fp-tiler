FROM node:22

RUN useradd -ms /bin/bash fieldpapers
RUN mkdir -p /home/fieldpapers && chown -R fieldpapers:fieldpapers /home/fieldpapers

USER fieldpapers

WORKDIR /home/fieldpapers
ADD . /home/fieldpapers/

RUN npm install

VOLUME ["/home/fieldpapers"]
EXPOSE 8080

CMD npm start
