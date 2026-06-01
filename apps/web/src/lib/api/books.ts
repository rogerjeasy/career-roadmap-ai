import { apiClient } from "./client";

export type BookStatus = "reading" | "queued" | "done";

export interface Book {
  id: string;
  title: string;
  author: string;
  why: string;
  status: BookStatus;
  tag: string;
  phase: string;
  takeaways: string[];
  createdAt: string;
}

export interface BookCreateInput {
  title: string;
  author?: string;
  why?: string;
  status?: BookStatus;
  tag?: string;
  phase?: string;
  takeaways?: string[];
}

export type BookUpdateInput = Partial<BookCreateInput>;

export const booksApi = {
  async list(): Promise<Book[]> {
    const { data } = await apiClient.get<Book[]>("/api/v1/books");
    return data;
  },

  async get(id: string): Promise<Book> {
    const { data } = await apiClient.get<Book>(`/api/v1/books/${id}`);
    return data;
  },

  async create(input: BookCreateInput): Promise<Book> {
    const { data } = await apiClient.post<Book>("/api/v1/books", input);
    return data;
  },

  async update(id: string, input: BookUpdateInput): Promise<Book> {
    const { data } = await apiClient.patch<Book>(`/api/v1/books/${id}`, input);
    return data;
  },

  async remove(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/books/${id}`);
  },
};
