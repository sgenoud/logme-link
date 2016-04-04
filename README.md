<p align="center">
    <img width="250px" src="https://raw.githubusercontent.com/sgenoud/logme-link/master/artwork/logo.png">
</p>


The Apple TV does not have web view, and therefore does not allow you to do
oauth on the device.

Logme Link is a simple server (written in python3) that allows you to give your
user a link that they can enter in their phone/tablet/computer. They can then
log in via this device (and it will then be available on the computer).


## Running the server

In order for the server to run you need to have a redis instance running. You
can then just call your server with:

`python3 server.py`

That's it, your server will then listen on the port 8080 of your localhost.

Note that this repository also contains a Dockerfile and a docker-compose
configuration for easy docker deployment.


## API

We need to introduce 2 concept:

* The **secret** corresponds to the value that is kept between the client and the
  server. This is what allows the Apple TV client to request the auth
  information
* The **key** corresponds to the code give to the user so that she can log into
  the system

#### `POST /_create`

The body posted should be json encoded and has the following values:

* `service`: the service to connect to (now supports only 'pocket')
* `key` (optional): a pre generated key that will be transmitted to the user
* `final_redirect_url` (optional): a url to redirect the client once her
  authorization has been confirmed

For different service additional information must (or can) be provided

* *Pocket*
    * `token`: the request token from the API


The call will return a json object with the following values:

* `secret`: the shared secret for the client app to request the auth info 
* `url`: the redirection url to offer the client
* `key`: the client key that will be exposed to the client


#### `GET /_info/:secret`

Returns the information related to the secret. Can take the query parameter
`wait=registered` or `wait=redirected` to wait for more information to be
returned (with a timeout of 30 seconds).

returns a json document with the values:

* `service`: the service related to this secret
* `redirected`: a boolean indicating if a user has been redirected to the service
* `registered`: a boolean indicating if the user is now registered 

Additionally the different service expose the variables that are passed to them
at creation as well.

#### `GET /_isup`

A simple sanity check (can be used to make sure the service is up with a tool
like pingdom).

#### `GET /:key`

Redirects the user to the service related to the `key`. When this endpoint is
called changed the `redirected` status to `True`.

#### `GET /register/:key`

The endpoint where the 3rd party should redirect to. If a `final_redirect_url`.
When this endpoint is called changed the `registered` status to `True`.



## Configuration

The server configuration is done via environment variables:

* `MY_URL` (defaults to `http://localhost:8080`): the base url that should be
  returned of the server (use for redirects and link generation). 
* `KEY_TTL` (defaults to 300): the number of seconds that keys will live - in
  other word the time you give your users to log in.

* `HOST` (defaults to `0.0.0.0`): where to listen for calls
* `PORT` (defaults to `8080`): port to listen to

* `REDIS_HOST` (defaults to `localhost`): where to find the redis instance
* `REDIS_PORT` (defaults to `6379`): on which port you find the redis instance


## Create another service

To create a new service you can simply create a package exposing the following
(async) methods:

* `async def parse_creation(request_body, request_qs=None)`: receives the data
  from the `_create` call and returns the information that needs to be saved to
  request more info.
* `async def redirect_url(info, redirect_uri)`: takes the info saved by the
  `parse_creation` function, as well as the uri to be redirected to (which will
  typically be the `/register/:key` url and outputs the link to be redirected
  to.

You can register it by adding it to the SERVICES dict. Pull requests welcome!


The LogMe Link logo icon has been created by Yaroslav Samoilov from the Noun
Project.
