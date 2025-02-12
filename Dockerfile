FROM node:22

RUN useradd -ms /bin/bash fieldpapers
RUN mkdir -p /home/fieldpapers/.npm && chown -R fieldpapers:fieldpapers /home/fieldpapers/.npm

USER fieldpapers

WORKDIR /home/fieldpapers
ADD . /home/fieldpapers/

RUN npm install

VOLUME ["/home/fieldpapers"]
EXPOSE 8080

CMD npm start
