// Arduino Nano Code for LED Simulation via Serial
const int ledPin = LED_BUILTIN; // Built-in LED on pin 13

void setup() {
  pinMode(ledPin, OUTPUT);    // Set the LED pin as output
  Serial.begin(9600);         // Initialize serial communication at 9600 baud
}

void loop() {
  if (Serial.available() > 0) { // Check if data is available on the serial port
    char command = Serial.read(); // Read the incoming byte
    if (command == '1') {
      digitalWrite(ledPin, HIGH); // Turn LED ON for Access Granted
    } else if (command == '0') {
      digitalWrite(ledPin, LOW);  // Turn LED OFF for Access Denied
    }
  }
}