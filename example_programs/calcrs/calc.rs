// This example program parses arithmetic expressions in a recursive descent parser.
// Copyright (c) 2023 Robert Bosch GmbH
// SPDX-License-Identifier: AGPL-3.0

use std::env;
use std::fs;
use std::io::{self, Read};
use std::char;
use std::iter::Peekable;
use std::num;

struct Parser<I> 
where
    I: Iterator<Item = char>,
{
    chars: Peekable<I>,
}


impl<I: Iterator<Item = char>> Parser<I> {
    /// Create a new parser instance from an iterator which iterates characters. The iterator is usually built from
    /// `str::chars` for parsing `str` or `String` values.
    pub fn new(it: I) -> Self {
        Parser {
            chars: it.peekable()
        }
    }

    fn peek(&mut self) -> Option<char> {
        self.chars.peek().copied()
    }

    fn next(&mut self) -> Option<char> {
        while let Some(c) = self.chars.next() {
            if !c.is_whitespace() {
                return Some(c);
            }
        }
        None
    }

    fn parse_number(&mut self) -> i64 {
        let mut number_str = String::new();
        while let Some(c) = self.peek() {
            if c.is_ascii_digit() {
                number_str.push(c);
                self.next();
            } else {
                break;
            }
        }
        match number_str.parse::<i64>() {
            Ok(res) => res,
            Err(e) => match e.kind() {
                //Lets tolerate overflow errors for matching our grammar
                num::IntErrorKind::PosOverflow => 1,
                _ => panic!("Could not parse number! Got {}",number_str ),
                
            }
        }
    }

    fn parse_factor(&mut self) -> i64 {
        let current_char = self.peek().expect("Unexpected end of input");
        if current_char == '(' {
            self.next();
            let result = self.parse_expr();
            let ch = self.next().expect("Unexpected end of input"); 
            if ch != ')'{
                panic!("Expected closing parenthesis! Got {}",ch );
            }
            result
        } else {
            self.parse_number()
        }
    }

    fn parse_term(&mut self) -> i64 {
        let mut result = self.parse_factor();
        while let Some(current_char) = self.peek() {
            match current_char {
                '*' => {
                    self.next();
                    result *= self.parse_factor();
                }
                '/' => {
                    self.next();
                    let factor = self.parse_factor();
                    // Prevent divide by zero
                    result /= match factor {
                        0 => 1,
                        _ => factor,
                    };
                }
                _ => break,
            }
        }
        result
    }

    fn parse_expr(&mut self) -> i64 {
        let mut result = self.parse_term();
        while let Some(current_char) = self.peek() {
            match current_char {
                '+' => {
                    self.next();
                    result += self.parse_term();
                }
                '-' => {
                    self.next();
                    result -= self.parse_term();
                }
                _ => break,
            }
        }
        result
    }

    fn parse(&mut self) -> i64 {
        let res = self.parse_expr();
        if let Some(current_char) = self.peek() {
            panic!("Expected character! Got {}", current_char )
        }
        res
    }
}

fn parse_calc(data: &str)  {
    let mut parser = Parser::new(data.chars());
    parser.parse();
}

fn main() {
    let args: Vec<String> = env::args().collect();

    let input_string = if args.len() > 1 {
        let filename = &args[1];
        match fs::read_to_string(filename) {
            Ok(content) => content,
            Err(error) => {
                eprintln!("Error reading file: {}", error);
                return;
            }
        }
    } else {
        let mut input_string = String::new();
        match io::stdin().read_to_string(&mut input_string) {
            Ok(_) => (),
            Err(error) => {
                eprintln!("Error reading from stdin: {}", error);
                return;
            }
        }
        input_string
    };

    // Process the input_string here (you can print it as an example)
    println!("Input string: {}", input_string);
    parse_calc(&input_string);

}
 