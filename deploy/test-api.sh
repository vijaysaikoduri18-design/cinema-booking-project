#!/bin/sh
# Smoke test through Nginx. Usage: ./test-api.sh http://WEB_VM_PUBLIC_IP
BASE=${1:-http://localhost}
curl -s -X POST $BASE/users/register -H 'Content-Type: application/json' \
  -d '{"name":"Ravi","email":"ravi@example.com","password":"secret123"}'; echo
TOKEN=$(curl -s -X POST $BASE/users/login -H 'Content-Type: application/json' \
  -d '{"email":"ravi@example.com","password":"secret123"}' | sed 's/.*"token":"\([^"]*\)".*/\1/')
echo "Movies:";  curl -s $BASE/products/movies; echo
echo "Shows:";   curl -s $BASE/products/shows; echo
echo "Book seats A1,A2 for show 1:"
curl -s -X POST $BASE/orders/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"showId":1,"seats":["A1","A2"]}'; echo
echo "My bookings:"; curl -s $BASE/orders/ -H "Authorization: Bearer $TOKEN"; echo
