const net = require('node:net');
const socket = net.createConnection(process.argv[2]);
socket.on('error', () => process.exit(1));
socket.on('close', () => process.exit());
process.stdin.pipe(socket);
socket.pipe(process.stdout);
